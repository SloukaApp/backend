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
- Registration creates an unconfirmed account and a one-time email confirmation, without issuing access/refresh tokens. Send confirmation mail outside the DB transaction through a Protocol adapter.
- Successful confirmation automatically logs the user in: consume the confirmation, mark the email confirmed through UsersService, check the device limit, and persist the device/refresh authorization in one transaction; return the access/refresh pair after successful commit.
- Confirmation tokens are six cryptographically random case-sensitive ASCII letters/digits, stored as SHA-256 hashes and never logged. Current configurable defaults: 900-second lifetime, 60-second resend cooldown. Resend verifies email/password and revokes earlier confirmations; changing the policy requires a separate decision.
- The separate login endpoint verifies credentials and confirmed email before issuing tokens. Unconfirmed users cannot log in or access learning functions.

## Devices

- Own `devices` and `refresh_tokens`; a device represents an account authorization session. Each login or successful confirmation creates a server-generated device ID. Refresh continues the same session.
- Count active devices by valid authorization, not historical refresh rows. Push subscription data belongs to notifications; disabling/revoking push never logs a device out.

## Implementation Notes

- Device lists include inactive history. No GET confirmation, password recovery, or account-deletion endpoint is implemented.
- Confirmation mail contains the code and app instructions, not a link or HTTP API details. Set Date and a unique Message-ID before SMTP; retain both across retries of the same message. SMTP runs after commit: delivery failure returns 503 but leaves the account/confirmation saved; retry through resend after cooldown. SMTP retries can duplicate delivery; only the latest non-revoked code is valid.
- Registration stores the client-provided consent version; backend does not supply legal text. Confirmation returns a token pair; registration does not.
- Account row locks through UsersService serialize issuance, refresh, resend and password changes; refresh/confirmation rows are also locked. Keep the dependency `auth → users`; HTTP auth dependencies in users do not reverse the service dependency.
- Rate limiting uses Redis TIME and an approximate sliding window counter: `current + previous * (1 - elapsed / window)`. Each Lua call checks all supplied budgets before incrementing them. If that call rejects the request, those counters and TTLs are unchanged. TTL is two windows after the last increment. Keys share `{rate_limit}` and use `REDIS__KEY_PREFIX`. Resend consumes only the shared API IP budget.
- Retry-After is rounded up to at least one second; competing requests may consume the recovered budget. Redis counters are independent of DB rollback; Redis AOF everysec can lose recent increments on failure.
- Client IP comes from the application's single ProxyHeadersMiddleware, restricted by `APP__TRUSTED_PROXIES`. Keep Uvicorn `--no-proxy-headers` to avoid a second forwarding-trust layer.
