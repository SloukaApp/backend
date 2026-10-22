FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder-base

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

FROM builder-base AS dev

ENV UV_COMPILE_BYTECODE=0

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "uvicorn", "src.main:create_app", "--factory", "--reload", "--host", "0.0.0.0", "--port", "8000"]

FROM builder-base AS builder-prod

ENV UV_NO_DEV=1

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

FROM python:3.14-slim-bookworm AS prod

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

COPY --from=builder-prod --chown=nonroot:nonroot /app/.venv /app/.venv
COPY --from=builder-prod --chown=nonroot:nonroot /app/src /app/src
COPY --from=builder-prod --chown=nonroot:nonroot /app/migrations /app/migrations
COPY --from=builder-prod --chown=nonroot:nonroot /app/alembic.ini /app/alembic.ini
COPY --from=builder-prod --chown=nonroot:nonroot /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH"

USER nonroot

CMD ["python", "-m", "uvicorn", "src.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
