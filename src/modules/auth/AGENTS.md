# Auth Module Rules

Inherits the root AGENTS.md. Public interface: `AuthService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

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
- Login rate limiting counts all admitted login checks, including successful logins and nonexistent accounts: 10 per approximate 15-minute sliding window counter per normalized input email–IP pair in Redis; subsequent attempts return 429 with Retry-After. Accounting is atomic across replicas, with automatic recovery and no permanent lockout. Refresh does not consume it. Login also limits all admitted requests to 60 per minute per IP. Both budgets are checked and consumed atomically through FastAPI Depends before the DB transaction; AuthService contains no rate-limit logic. Confirmation counts all admitted checks: 5 per 900 seconds per normalized input email and 20 per 900 seconds per IP, atomically across both budgets; resend never resets them. Redis failure returns 503 for login/confirmation. Redis keys intentionally contain clear normalized email/IP by explicit user decision; never log them. Log failed attempts without credentials or personal data.
- Verify account existence and non-deletion on each authenticated request; a valid JWT signature alone is insufficient. Deleted accounts perform no operations.
- Return 401 for missing/expired access, invalid refresh, or a deleted account. An unconfirmed account receives 403 on learning routes.

## Registration & Email Confirmation

- Provide separate registration, email-confirmation, and login endpoints. These endpoints require no access token; refresh requires only a valid refresh token.
- Registration creates an unconfirmed account and a one-time email confirmation, without issuing access/refresh tokens. Send confirmation mail outside the DB transaction through a Protocol adapter.
- Successful confirmation automatically logs the user in: consume the confirmation, mark the email confirmed through UsersService, check the device limit, and persist the device/refresh authorization in one transaction; return the access/refresh pair after successful commit.
- Confirmation tokens are random, stored only as hashes, and never logged. Do not grant authorization from a used, revoked, or expired confirmation. Confirmation lifetime and reissue policy require a separate decision; do not invent defaults.
- The separate login endpoint verifies credentials and confirmed email before issuing tokens. Unconfirmed users cannot log in or access learning functions.

## Devices

- Own `devices` and `refresh_tokens`; a device represents an installation/account authorization, not a push subscription. Installation identity is unique per `(user_id, installation_id)`; switching accounts must not transfer authorization.
- Count active devices by valid authorization, not historical refresh rows. Push subscription data belongs to notifications; disabling/revoking push never logs a device out.
