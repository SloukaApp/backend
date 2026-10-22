# Backend Rules

Work from `backend/`. Import root is `src`.

## Setup & Commands

```bash
uv sync                      # sole package manager; commit uv.lock
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
```

Run these commands for application code changes; report failures or commands that could not run. Documentation-only changes require a consistency review. Use only `uv`, never `pip` / `poetry` / `pipenv`; commit generated `uv.lock` changes, never hand-edit it. New dependencies require approval. FastAPI `Depends` is the DI mechanism; no DI containers, sync DB drivers, or alternate ORMs.

Stack is fixed: Python 3.14, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, PostgreSQL 17, Redis, Taskiq + taskiq-redis, httpx, Pydantic v2, pydantic-settings, PyJWT, pwdlib[argon2].

```text
src/main.py            # lifespan; explicit router + handler registration
src/core/              # config, db, redis, uow, errors, http_errors, schemas, logging, dependencies.py
src/modules/<name>/{router,service,dto,domain,errors,http_errors,repository,models,schemas,adapters,dependencies}.py
src/worker/            # bootstrap.py, broker.py, tasks/
migrations/
```

## Module Responsibilities

| Module | Owns | Local rules |
| --- | --- | --- |
| `users` | User accounts, email, password hashing and verification | [users/AGENTS.md](src/modules/users/AGENTS.md) |
| `auth` | Authentication workflows, access tokens, refresh tokens and devices | [auth/AGENTS.md](src/modules/auth/AGENTS.md) |
| `decks` | Decks/cards, stored learning state, tags, visibility and copying | [decks/AGENTS.md](src/modules/decks/AGENTS.md) |
| `practice` | Sessions, accepted answers and scheduling calculations | [practice/AGENTS.md](src/modules/practice/AGENTS.md) |

Read the local rules of each module affected by a change, including cross-module workflows. Other capabilities (`stats`, `settings`, `notifications`, `exercises`) remain planned; do not create them until needed.

Planned ownership: `auth` owns `devices` (installations and authorization); `notifications` owns `push_subscriptions` linked by `device_id`, plus delivery records. Push tokens, permission and push-disable state belong to the subscription, not the device. Notifications uses public auth operations to verify devices; auth does not call notifications. Disabling push never revokes authorization. Before sending, verify the account/device is still authorized.

Statistics are computed from `activity_logs`; learned status and difficulty come from `cards`. Do not introduce `user_stats` or stored calendars. Activity remains a business fact, not a mutation audit.

## Module Boundaries & Public Contracts

- Modules own business capabilities and invariants. Do not split by entity name or create unused modules. Discuss boundary changes before implementing them.
- `service.py` exposes the public service class with typed instance methods; helpers are private. Other modules may import only this public interface, its DTOs, and documented public exceptions from `errors.py`, except for projection queries below. Public exceptions are part of the service contract; callers may catch them to translate their meaning for the owning workflow. Routers and workers call the service owning the use case.
- Assemble service instances explicitly in module `dependencies.py` using FastAPI `Depends`, and in `worker/bootstrap.py` for workers. Inject collaborating service instances through constructors; services never import or invoke FastAPI dependency providers or construct collaborators inside business methods.
- Put service input/result DTOs in `dto.py` as Pydantic v2 models. Keep HTTP request/response schemas in `schemas.py`; routers translate them to/from service DTOs. Keep inbound and outbound types separate and create only types needed by existing operations. ORM instances may pass from the owning repository to its service internally; public service inputs/results never contain ORM instances or lazy collections. When converting ORM instances with `model_validate`, use `from_attributes=True` and explicitly load all required attributes first.
- Each cross-module use case has one explicit owner: the module responsible for the business outcome. Record the owner and dependency direction alongside the first implementation. The owner coordinates public operations; participants never call back into the owner. Keep inter-module application dependencies acyclic. If no existing module is a natural owner, discuss a dedicated workflow module or revised boundaries before introducing one; do not put orchestration in `core` or routers.
- Each table has one owning module. Only that module's repository performs application writes. Foreign keys across modules are allowed and use string table/column targets, without importing the target ORM class. A foreign key expresses database integrity, not an application dependency or permission to navigate foreign objects.
- Keep ORM `relationship()` navigation within a module by default. Cross-module references use scalar IDs and public service queries. `TYPE_CHECKING` imports and string relationship annotations still couple modules and are not a workaround for this boundary. Register all model mappings explicitly in the Alembic metadata aggregator.
- Exception for read-only cross-module queries: a repository implementing an explicit search, statistics, or reporting projection may import the required foreign ORM mappings and use JOINs/aggregates. Keep imports local to that repository's responsibility, return materialized projection data, and never mutate foreign objects or expose ORM results. This exception does not permit command workflows to bypass public services or ownership/visibility checks.

## UoW & Transactions

- Inject one `UnitOfWork` into the request/worker operation's service constructors. All participants share it: FastAPI uses the same cached `get_uow` dependency (no `use_cache=False`); workers wire it explicitly. Services are operation-scoped, never global singletons. Store `self.uow`; obtain `self.uow.session` during method execution and pass it only to repositories.
- The router/worker must enter `async with uow` before any database-backed service call, including reads. Construction before entry is allowed; session access outside a context must fail. Only the boundary manages the context; services/repositories never open, commit, roll back, or close it. No manual commits, nested contexts/transactions, or concurrent use.
- Sequential contexts of the same UoW are allowed. Each creates a fresh session, commits on success, rolls back on body/commit failure, and always closes. Never reuse completed sessions/transactions. A failed stage stops the scenario; retries start a new operation/UoW. Earlier commits remain committed. Session factory: `expire_on_commit=False`, `autoflush=False`.
- External HTTP/API, SMTP, push, and broker publication run outside DB transactions. A subsequent context re-checks access and relevant state before writing. Redis cache/rate-limit calls are allowed but are not atomic with PostgreSQL. External side effects cannot be undone by DB rollback.
- Between stages pass only materialized DTOs/IDs. Build DB-backed service results and response DTOs before context exit; flush and explicitly load/refresh required generated values first, without lazy loading. `return` inside the context is allowed: commit must succeed before it returns.

Single database stage:

```python
async with uow:
    result = await auth_service.register_user(data.email, data.password)
    return ReadUser(**result.model_dump())
```

External read/computation between database stages (`apply` re-checks access and state):

```python
async with uow:
    prepared = await service.prepare(data)

external_result = await service.fetch_external(prepared)

async with uow:
    result = await service.apply(prepared, external_result)
    return ResponseSchema(**result.model_dump())
```

## Code Conventions & Invariants

| File | Responsibility |
| --- | --- |
| `router.py` | Validate HTTP input, sequence service stages, map results to response schemas. |
| `service.py` | Orchestrate use cases and business decisions. |
| `dto.py` | Pydantic service input/result models. |
| `domain.py` | Pure business rules; time is an explicit parameter. |
| `errors.py` | Transport-independent exceptions forming the public service contract. |
| `http_errors.py` | HTTP mappings for public exceptions, wired by `main.py`. |
| `repository.py` | Typed async queries with `AsyncSession` as the first argument. |
| `models.py` | ORM mappings. |
| `schemas.py` | HTTP request/response models. |
| `adapters.py` | External-client Protocols and implementations. |
| `dependencies.py` | Dependency assembly for API handlers. |

- Routers contain no SQL or business decisions. Services never import transport. Domain code has no I/O, session, configuration, or clock access. Services depend on external-client `Protocol` interfaces; concrete adapters are wired in composition roots.
- Absolute imports rooted at `src`; relative cross-module imports forbidden. `core` never imports `modules` (sole exception: the ORM metadata aggregator Alembic needs). Beyond module skeletons, create only files with real content; no speculative helpers or empty packages.
- Generate UUIDv7 in application code; never assign generated/trigger-maintained columns such as `updated_at`.
- Store event instants in UTC using `timestamptz`; derive local dates using the user's validated IANA timezone. Keep local reminder times and delivery dates distinct from instants.
- Store structured content in related PostgreSQL tables, not JSONB, arrays of answer options, or JSON encoded as text.
- `numeric` columns computed in `Decimal`; never binary `float`. No N+1 aggregates.
- Translate DB violations, never leak 500: `23505`→409, `23503` missing parent on write→404, `23503` NO ACTION blocking delete→409, `23514`→409 or 422 by meaning.
- REST/JSON under `/api/v1`, OpenAPI at `/api/v1/openapi.json` with declared response + error schemas. Incompatible changes require a new API version.
- Statuses: 401 authentication failure · 403 operation forbidden by account state · 404 object missing **or** no ownership right · 409 duplicate, event conflict, limit reached · 422 invalid input · 429 + `Retry-After` · 502/503 upstream. Never answer an existence question with 403.
- Filter ownership by `user_id` in SQL; reach children through their parent. Trust forwarded IP only for configured trusted proxies. Own lists: `limit`/`offset` in, `{items, total, limit, offset}` out. Never silently ignore an accepted parameter — apply it or reject.
- External clients are created and closed by the lifecycle of the process using them, with explicit timeouts and bounded retries. FastAPI manages API resources in lifespan; a separately launched worker manages its resources in its own startup/shutdown. If a queue consumer is embedded in the API process, lifespan manages its start/stop and resource cleanup. Upstream bodies pass a dedicated external Pydantic schema before parsing; failure or parse error is an error, never an empty result; missing data never invented. Per-account rate limits in Redis count cache hits. Upstream outage must not break unrelated modules.
- Worker deps assembled explicitly in `worker/bootstrap.py`. Delivery state keyed so a rerun creates no new logical unit; failure never marked sent; one unit's failure doesn't abort the batch; periodic cleanup respects retention and answer idempotency.
- pydantic-settings with `env_nested_delimiter="__"`, cached `get_settings()`; the migrator reads DB settings only. Structured logging with propagated request id.

## Error Handling

- Define module errors in `errors.py` as `ApplicationError` subclasses with an `Error` suffix. They are part of the public service contract; document them on service methods. Carry semantic data only, with no HTTP imports, statuses, headers, or response text.
- Define `ERROR_MAPPINGS` in module `http_errors.py`; assemble them explicitly in `main.py` with `build_application_error_handler(*ERROR_MAPPINGS, ...)`. Static responses and typed translator functions are supported; services and workers never import HTTP mappings.
- Register the same handler for `ApplicationError` and `Exception`. Matching is exact; duplicates fail at startup, unmapped/unexpected errors return safe 500. Responses use explicit safe text, never `str(exc)`. Preserve FastAPI validation; declare expected HTTP errors using `ErrorResponse` in OpenAPI.
- Routers need no error-handling `try/except`. Services catch errors only for recovery or workflow-specific translation; workers apply their own failure/retry policy.
- Translate known DB violations around repository `flush()` using SQLSTATE and constraint identity. UoW rolls back/closes; it knows no module semantics. Deferred constraints need explicit commit-time translation when introduced; unknown DB failures are not business conflicts.

Example for a future auth operation (add only errors needed by real operations):

```python
# modules/auth/errors.py
from src.core.errors import ApplicationError


class LoginRateLimitedError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__()


# modules/auth/http_errors.py
from src.core.http_errors import HttpErrorResponse, map_error
from src.modules.auth.errors import LoginRateLimitedError


def rate_limit_response(error: LoginRateLimitedError) -> HttpErrorResponse:
    return HttpErrorResponse(
        429, "Too many requests", {"Retry-After": str(error.retry_after_seconds)}
    )


ERROR_MAPPINGS = (map_error(LoginRateLimitedError, rate_limit_response),)
# Static alternative: map_error(SomeError, HttpErrorResponse(409, "Conflict"))
```

## Boundaries & Safety

**Always**

- Secrets from environment only; read them via `src/core/config.py`.
- Store personal data required by a feature in its intended tables, including account email and necessary profile data.

**Ask first**

- New dependency; changing API version prefix or a response contract incompatibly; auth TTLs or device limit; deletion/retention semantics; any migration that drops or rewrites data.

**Never**

- Hardcode a secret default in code, or edit `.env`.
- Log plaintext credentials, tokens, or personal data; persist plaintext passwords or tokens.
- Bypass a DB constraint from application code.
- Generic CRUD base repositories.
- Bare `# type: ignore`, `Any` escaping, or untyped defs (mypy strict).

## Migrations

- Every database schema change uses Alembic, including indexes, constraints, functions, and triggers. Python-only changes need no migration. Keep mappings and DB schema aligned, including composite unique keys referenced by foreign keys. Never edit migrations already applied elsewhere.
- For schema/migration changes, run the following cycle against a dedicated disposable database, never production or a shared development database:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic check
```

## Workflow Rules

- Do not report completion with lint/type failures outstanding.
- Where these rules conflict with observed code, stop and ask — do not silently pick a side.
