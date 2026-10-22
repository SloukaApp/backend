# Users Module Rules

Inherits the root AGENTS.md. Public interface: `UsersService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership & Dependencies

- Own user records, account state, email normalization, and password hashing/verification. Do not own refresh tokens or devices.
- Other modules access users through public service methods and DTOs, and may catch documented public exceptions; never access the repository or ORM models.
- Dependency direction is `auth → users`; users never calls auth. Auth coordinates registration, password changes, and account deletion when token issuance/revocation is involved.
- Credential verification returns a safe user DTO or an authentication failure result; never expose password hashes in public DTOs, HTTP responses, or logs.

## Passwords

- Passwords require at least 8 characters. Do not impose alphabet, case, digit, or special-character composition rules; special characters are allowed. Hash passwords with Argon2. Never persist, return, or log plaintext passwords.
- Keep normalization and password handling inside this module. Database constraints enforce uniqueness; a prior lookup alone does not prevent concurrent duplicates.

## Account Data

- Require a valid unique email and explicit consent at registration; store consent acceptance time and text version in `users`.
- Store email confirmation state, onboarding completion, IANA timezone and reminder settings in `users`; no separate consent/settings tables. Completing onboarding is idempotent and persists across logins.
- Account deletion requires explicit confirmation and the current password. Remove the account's learning data and authorization immediately; delete/anonymize personal data within 30 days. Other users' independent copies remain intact.
