# Slouka backend

Python 3.14, FastAPI, PostgreSQL 17, Redis. Команды выполняются из `backend/`;
импорты начинаются с `src`.

## Сервисы

| Production | Адрес |
| --- | --- |
| API (базовый URL) | `https://api.slouka.csmmark.me/api/v1` |
| Swagger | [API Docs](https://api.slouka.csmmark.me/api/v1/docs) |
| OpenAPI | [openapi.json](https://api.slouka.csmmark.me/api/v1/openapi.json) |
| Веб-почта Roundcube | [webmail.slouka.csmmark.me](https://webmail.slouka.csmmark.me) |
| CI/CD | [GitHub Actions](https://github.com/SloukaApp/backend/actions) |
| Образы backend | [GitHub Packages](https://github.com/orgs/SloukaApp/packages/container/package/backend) |

| Локально | Адрес |
| --- | --- |
| Swagger | [localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) |
| OpenAPI | [localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json) |
| Mailpit | [localhost:8025](http://localhost:8025) |
| pgAdmin | [localhost:5050](http://localhost:5050), порт меняется через `PGADMIN_PORT` |

## Локальный запуск

Нужны Docker Compose и uv. Создайте `.env` из [.env.template](.env.template),
задайте пароль БД и соответствующий `DB__DSN`, случайный `AUTH__JWT_SECRET`,
`PGADMIN_DEFAULT_EMAIL` и непустой `PGADMIN_DEFAULT_PASSWORD`.

```bash
uv sync
make config
make up
```

Make использует `docker-compose.yaml` и `docker-compose.override.yaml`:
собирает dev-образы, запускает PostgreSQL, Redis, Mailpit, pgAdmin и API с reload.
Migrator применяет `alembic upgrade head` перед запуском API.

`make stop` останавливает сервисы, `make down` удаляет контейнеры и сети,
сохраняя `var/`. Остальные команды: `make build`, `make logs`, `make ps`.

Порты доступны только через loopback. С хоста PostgreSQL — `localhost:5432`,
SMTP Mailpit — `localhost:1025`. В pgAdmin сервер БД — `database:5432`,
параметры входа — `DB__USER`, `DB__PASSWORD`, `DB__NAME` из `.env`.
Для URL-спецсимволов в пароле БД задайте `DB__CONTAINER_DSN` с percent-encoding.

При запуске API вне Docker **сначала обеспечьте доступ к Redis**: dev Compose
не публикует его порт. Используйте локальный Redis или дополнительный локальный
Compose override с портом `127.0.0.1:6379:6379`. Затем поднимите PostgreSQL/Mailpit,
примените миграции и запустите `uv run uvicorn src.main:create_app --factory
--no-proxy-headers --reload`. DSN и SMTP в `.env` должны указывать на доступные с хоста адреса.

## Проверки

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest
```

PR в `main` запускает эти проверки. Если push или PR меняет только Markdown-файлы,
пайплайн пропускается; ручной запуск остаётся доступен. Отсутствие собранных тестов в CI пока
допускается с предупреждением.

## Production и деплой

На VPS используются `docker-compose.yaml` и `docker-compose.prod.yaml`,
каталог `/opt/slouka`, Compose-проект `slouka`. Окружение — `production.env`
по [.env.prod.template](.env.prod.template), права `0600`. Dev override и Make не используются.

Push в `main` с изменениями помимо Markdown или ручной запуск workflow на `main` выполняет:

1. Проверки, сборку target `prod` и публикацию образа в GHCR с тегом SHA коммита.
2. SSH-вход по паролю и скачивание образа по digest с временным `GITHUB_TOKEN`.
3. Миграции из того же образа, обновление backend и ожидание healthcheck.
4. Проверку HTTPS OpenAPI. При ошибке job завершается неуспешно; автоматического отката нет.

Временные данные входа в GHCR удаляются после job. Compose-файлы, `deploy/`
и `production.env` обновляются на сервере вручную; автодеплой не пересоздаёт инфраструктуру.
`BACKEND_IMAGE` в серверном env пайплайн не переписывает: для ручного запуска
указывайте актуальный digest. Ручное скачивание приватного образа требует `docker login ghcr.io`.

| Настройки GitHub | Имя | Назначение |
| --- | --- | --- |
| Repository variable | `DEPLOY_ENABLED` | `true` включает деплой, `false` оставляет проверки и публикацию |
| Environment `production`: variable | `PROD_SSH_HOST` | IP или DNS-имя VPS |
| Environment `production`: variable | `PROD_SSH_USER` | Пользователь с доступом к Docker и `/opt/slouka` |
| Environment `production`: variable | `PROD_SSH_PORT` | SSH-порт, по умолчанию 22 |
| Environment `production`: secret | `PROD_SSH_PASSWORD` | Пароль SSH-пользователя |

### Первоначальное развёртывание

1. На Linux VPS `amd64` установить Docker Compose с поддержкой `--wait` и curl.
2. С `DEPLOY_ENABLED=false` выполнить workflow на `main`, получить опубликованный digest.
3. Разместить оба Compose-файла и `deploy/` в `/opt/slouka`, заполнить `production.env`,
   включая `BACKEND_IMAGE`. Создать каталоги данных с правами записи для контейнеров;
   `var/stalwart/etc` и `var/stalwart/data` должны принадлежать UID/GID `2000:2000`.
4. Направить `api.slouka`, `mail.slouka`, `webmail.slouka` в DNS-зоне `csmmark.me` на VPS.
   Открыть SSH и TCP 80/443/25/465/993. Поднять инфраструктуру:

   ```bash
   cd /opt/slouka
   docker compose --project-name slouka --env-file production.env \
     -f docker-compose.yaml -f docker-compose.prod.yaml \
     up -d --no-deps database redis traefik stalwart roundcube
   ```

5. Настроить Stalwart через первоначальную админку `http://127.0.0.1:8080/admin`
   с SSH-туннелем `ssh -L 8080:127.0.0.1:8080 USER@VPS`: домен `slouka.csmmark.me`,
   администратора, ящик `noreply` с паролем `SMTP__PASSWORD`, ACME HTTP-01.
   Опубликовать MX, SPF, DKIM, DMARC в DNS-зоне; у VPS-провайдера задать PTR
   `mail.slouka.csmmark.me`. После первоначальной настройки перезапустить Stalwart.
6. После готовности PostgreSQL, Redis и почты включить `DEPLOY_ENABLED=true` и запустить workflow.

### Администрирование почты

Админка Stalwart доступна только через SSH-туннель:

```bash
ssh -L 8443:127.0.0.1:8443 USER@VPS
```

Для браузера временно сопоставьте `mail.slouka.csmmark.me` с `127.0.0.1`
в локальном hosts. Затем откройте [Stalwart Admin](https://mail.slouka.csmmark.me:8443/admin).
После работы закройте туннель и удалите локальное сопоставление.

## Данные и конфиги

Данные на VPS находятся в `/opt/slouka/var/` и не отслеживаются Git:

| Сервис | Каталог |
| --- | --- |
| PostgreSQL | `var/postgresql` |
| Redis | `var/redis` |
| Traefik: сертификаты HTTPS API и веб-почты | `var/traefik/acme` |
| Stalwart: настройки, почта и сертификаты SMTP/IMAP | `var/stalwart/etc`, `var/stalwart/data` |
| Roundcube: SQLite | `var/roundcube/db` |

Конфиги из `deploy/` подключаются только для чтения: `traefik/routes.yaml` — маршруты,
`roundcube/production.php` — HTTPS-прокси и проверка почтового TLS,
`roundcube/resources.conf` и `resources.ini` — лимиты Apache/PHP.
HTTPS-сертификаты получает и продлевает Traefik; почтовые — Stalwart через ACME HTTP-01.

## Правила разработки

[Общие правила](AGENTS.md) · [Auth](src/modules/auth/AGENTS.md) ·
[Users](src/modules/users/AGENTS.md) · [Decks](src/modules/decks/AGENTS.md) ·
[Practice](src/modules/practice/AGENTS.md). Контракты API — в Swagger/OpenAPI по ссылкам выше.
