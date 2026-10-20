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

- Hash passwords with Argon2. Never persist, return, or log plaintext passwords.
- Keep normalization and password handling inside this module. Database constraints enforce uniqueness; a prior lookup alone does not prevent concurrent duplicates.
