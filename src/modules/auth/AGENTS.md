# Auth Module Rules

Inherits the root AGENTS.md. Public interface: `AuthService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP handlers belong in `http_errors.py`
and are registered in `main.py`, never imported by services or workers.

## Ownership & Dependencies

- Own authentication workflows, access-token issuance, refresh-token/device records, one-time email confirmations, rotation, revocation, and login rate limiting.
- Depend on `UsersService` for user creation, credential verification, and account changes. Do not access user tables or password hashes directly. Read users/AGENTS.md for these workflows.
- Password change, account deletion, and logout-everywhere revoke all refresh tokens for the account in the same transaction as related account changes.
- Return tokens only in designated issuance/rotation responses. Never log or persist plaintext access/refresh tokens. Store only a hash of each random refresh token.

## Tokens, Devices & Login

- Access JWT lifetime is fixed at 30 minutes and never extended. Refresh lifetime is fixed at 30 days. Configuration validation rejects other TTLs.
- Rotate under `SELECT ... FOR UPDATE`: revoke the old token and create the new one in one transaction. Of two concurrent rotations exactly one succeeds. Used/revoked/expired refresh returns 401 and revokes nothing else.
- Logout revokes only that device. Issued access JWTs remain valid until `exp`, subject to the per-request account check.
- Keep one refresh token per device and an active-device limit of at least five. Serialize the limit check and issuance under a row lock. Reject login above the limit; never evict existing tokens.
- API middleware atomically checks the shared API IP budget and any additional route IP budget before body validation. The shared default is 60 requests per minute per IP. The additional defaults are 10 per minute per IP for login and 20 per 15 minutes per IP for confirmation. Requests admitted by middleware consume the IP budgets even if validation or an auth dependency later rejects them.
- After body validation and before the DB transaction, FastAPI Depends checks a separate Redis budget. Login allows 10 admitted checks per approximate 15-minute window per normalized input email–IP pair, including successful logins and nonexistent accounts. Confirmation allows 5 admitted checks per approximate 15-minute window per normalized input email across all IPs. Resend never resets that budget. Refresh consumes only the shared API IP budget. AuthService contains no rate-limit logic. A rejection returns 429 with Retry-After, and Redis failure returns 503. Redis keys intentionally contain clear normalized email/IP by explicit user decision. Keep them out of logs and log failed attempts without credentials or personal data.
- Verify account existence and non-deletion on each authenticated request; a valid JWT signature alone is insufficient. Deleted accounts perform no operations.
- Return 401 for missing/expired access, invalid refresh, or a deleted account. An unconfirmed account receives 403 on learning routes.

## Registration & Email Confirmation

- Provide separate registration, email-confirmation, and login endpoints. These endpoints require no access token; refresh requires only a valid refresh token.
- Registration creates an unconfirmed account and reserves a one-time email confirmation, without issuing access/refresh tokens. Publish the confirmation ID through a Protocol adapter after commit. AuthService derives the code for an active reservation. After the read transaction, the Taskiq worker passes the delivery data to MailService. The worker coordinates both public services.
- Successful confirmation automatically logs the user in: consume the confirmation, mark the email confirmed through UsersService, check the device limit, and persist the device/refresh authorization in one transaction; return the access/refresh pair after successful commit.
- Derive six case-sensitive ASCII letters/digits from HMAC-SHA256 over the confirmation ID using the dedicated confirmation secret. The API and worker use the same secret. Keep codes and their hashes out of storage and logs. Current configurable defaults: 900-second lifetime, 60-second resend cooldown, both measured from reservation. Resend verifies email/password and revokes earlier confirmations; changing the policy requires a separate decision.
- The separate login endpoint verifies credentials and confirmed email before issuing tokens. Unconfirmed users cannot log in or access learning functions.

## Devices

- Own `devices` and `refresh_tokens`; a device represents an account authorization session. Each login or successful confirmation creates a server-generated device ID. Refresh continues the same session.
- Count active devices by valid authorization, not historical refresh rows. Push subscription data belongs to notifications; disabling/revoking push never logs a device out.

## Password Reset

- Auth owns the reset workflow and reservations. The dependency direction is `auth → users`. Only UsersService writes the new password hash. Use the account row lock for reservation and consumption, in the same order as login, refresh and password change.
- Both reset endpoints are public. For a syntactically valid request, publish an opaque UUID after commit and return the same `202` for confirmed, unconfirmed, missing and cooldown-limited accounts. Only an eligible account outside the cooldown gets a reservation. The worker skips UUIDs without an active reservation. A publication failure returns the same `503` for all cases. A committed reservation is eligible for replacement after cooldown.
- Reset codes are six case-sensitive ASCII letters/digits derived using the confirmation secret and a reset-specific HMAC input. Only reservation metadata is stored. Configurable defaults are 900 seconds of validity and 60 seconds between reservations. A new reservation revokes the previous one. The worker checks reservation and account state before sending and before each retry.
- Reset requests use the shared API IP budget. Reset confirmation has separate budgets of 20 checks per IP and 5 per normalized email across all IPs, per approximate 900-second window by default. Reissuing a code never resets those budgets. Reject over-limit requests with `429` and `Retry-After`.
- An invalid, expired, revoked or consumed code yields the same `401`. A successful reset consumes the code, changes the password and revokes all refresh tokens in one transaction. Return `204` and let the client log in with the new password. An authenticated password change also revokes pending reset codes.

## Implementation Notes

- Device lists include inactive history. There are no GET confirmation or account-deletion endpoints.
- Confirmation mail contains the code and app instructions, not a link or HTTP API details. MailService retains Date and Message-ID across all SMTP attempts for the same confirmation and asks the worker to re-check the code through AuthService before retrying. A redelivered task derives the same code for an active reservation. A queue publication failure returns 503 and leaves the reservation saved. Retry through resend after cooldown.
- Registration stores the client-provided consent version; backend does not supply legal text. Confirmation returns a token pair; registration does not.
- Account row locks through UsersService serialize authorization, refresh, resend, email confirmation and password changes. Refresh also locks its token row. The confirmation endpoint locks the current confirmation row when consuming it. Keep the dependency `auth → users`; HTTP auth dependencies in users do not reverse the service dependency.
- Rate limiting uses Redis TIME and an approximate sliding window counter: `current + previous * (1 - elapsed / window)`. Each Lua call checks all supplied budgets before incrementing them. If that call rejects the request, those counters and TTLs are unchanged. TTL is two windows after the last increment. Keys share `{rate_limit}` and use `REDIS__KEY_PREFIX`. Resend consumes only the shared API IP budget.
- Retry-After is rounded up to at least one second; competing requests may consume the recovered budget. Redis counters are independent of DB rollback; Redis AOF everysec can lose recent increments on failure.
- Client IP comes from the application's single ProxyHeadersMiddleware, restricted by `APP__TRUSTED_PROXIES`. Keep Uvicorn `--no-proxy-headers` to avoid a second forwarding-trust layer.
