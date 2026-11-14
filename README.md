# Slouka backend

Python 3.14, FastAPI, PostgreSQL 17. Работать из `backend/`; импорты начинаются с `src`.
Шаблоны окружений в корне: `.env.template` для разработки и `.env.prod.template`
для production.

## Разработка

Создайте `.env` из `.env.template`; задайте пароль БД, соответствующий `DB__DSN`,
случайный `AUTH__JWT_SECRET` и непустой пароль pgAdmin. Секреты не коммитить.
Команды выполняются из `backend/`:

```bash
uv sync
make config
make up
```

База и Redis проходят healthcheck, migrator применяет `alembic upgrade head`,
затем запускается backend с reload. Применение миграций на общей/существующей БД
сначала согласуйте. `make stop` останавливает сервисы, `make down` удаляет
контейнеры/сеть, сохраняя `var/`; `make build`, `make logs`, `make ps` доступны отдельно.
Базовый `docker-compose.yaml` общий; `docker-compose.override.yaml` добавляет
Mailpit, pgAdmin, локальную сборку target `dev`, исходники и порты. `make up`
использует оба файла явно. Dev/prod запускать на разных
машинах/каталогах данных; это один Compose-проект в каждом окружении.

- API: http://localhost:8000/api/v1/docs
- Mailpit: http://localhost:8025, SMTP с хоста: localhost:1025
- pgAdmin: http://localhost:5050; PostgreSQL с хоста: localhost:5432

Опубликованные dev-порты привязаны к loopback. В pgAdmin сервер — `database:5432`,
база/пользователь/пароль из DB__NAME/DB__USER/DB__PASSWORD. Изменение env не меняет
пароль уже созданной учётной записи pgAdmin. Данные находятся в `var/pgadmin`.
В Compose DB DSN и Redis DSN заменяются на контейнерные; SMTP dev направлен на
`mailpit:1025`, без TLS. Для URL-спецсимволов в credentials задайте
DB__CONTAINER_DSN с percent-encoding. Не выводите разрешённую конфигурацию с секретами.

Для API вне Docker сначала поднимите инфраструктуру, затем примените миграции:

```bash
docker compose up -d --no-deps database redis mailpit
uv run alembic upgrade head
uv run uvicorn src.main:create_app --factory --no-proxy-headers --reload --host 127.0.0.1 --port 8000
```

В этом режиме DB/SMTP используют localhost из `.env`; Redis по умолчанию не
публикуется. Для запуска API на хосте добавьте **локальный** Compose override с
`redis.ports: ["127.0.0.1:6379:6379"]` и поднимите его явно либо используйте
отдельный локальный Redis по REDIS__DSN. Login/confirm-email требуют Redis.
Юридический текст согласия предоставляет клиент; backend сохраняет переданные
consent_version и время согласия.

## Production

Используются `docker-compose.yaml` и `docker-compose.prod.yaml`, проект `slouka`.
Backend и migrator скачивают один готовый образ из GHCR по digest; сборки на VPS
нет. PostgreSQL, Redis, Traefik, Stalwart и Roundcube используют теги конкретных
версий без digest. Dev override, Mailpit, pgAdmin и Makefile на сервере не нужны.

### Подготовка сервера

- Linux VPS `amd64` с Docker Engine, Compose plugin с поддержкой `--wait` и curl.
  SSH-пользователю нужны вход по паролю, доступ к Docker и каталогу `/opt/slouka`.
- В `/opt/slouka` разместить оба Compose-файла и папку `deploy/`. Создать каталоги
  из таблицы данных ниже с правами записи для соответствующих контейнеров.
  Конфиги и инфраструктура обновляются вручную;
  автодеплой их не передаёт.
- Создать `/opt/slouka/production.env` по `.env.prod.template`, права
  `0600`. Заполнить `BACKEND_IMAGE` опубликованным digest, параметры БД и `DB__DSN`,
  JWT secret, `ACME_EMAIL`, пароль ящика noreply и постоянный 24-символьный ключ
  `ROUNDCUBEMAIL_DES_KEY`. Оставить `APP_ENV_FILE=./production.env` из шаблона:
  он указывает backend и migrator, какой файл окружения загружать.
  Настоящий env хранится только на сервере.
- Приватный GHCR-образ при автодеплое скачивается с временным `GITHUB_TOKEN`:
  job имеет `packages: read`, данные входа удаляются после завершения.
  Для ручного скачивания вне CI нужен отдельный `docker login ghcr.io`.
- Настроить DNS для `api.slouka.csmmark.me`, `mail.slouka.csmmark.me` и
  `webmail.slouka.csmmark.me` на VPS. Открыть SSH и TCP 80/443, для почты — 25/465/993.
  Внешний API доступен через Traefik на HTTPS, БД и Redis публично не открываются.
- При первом запуске Stalwart пройти мастер через SSH-туннель к локальному 8080
  (`ssh -L 8080:127.0.0.1:8080 USER@VPS`, адрес `http://127.0.0.1:8080/admin`).
  Stalwart сам создаёт `config.json` в `var/stalwart/etc`; отдельного шаблона
  хранилища в `deploy/` нет, используются стандартные настройки RocksDB.
  Настроить домен `slouka.csmmark.me`, постоянного администратора, ящик
  `noreply@slouka.csmmark.me` с паролем из env, TLS для SMTP/IMAP и почтовые DNS
  записи MX, SPF, DKIM, DMARC и PTR. Для почтового ACME использовать HTTP-01 через
  существующий маршрут Traefik; публичный 443 уже занят Traefik.
  Compose не создаёт почтовые аккаунты и не настраивает почтовый ACME.

Начальный запуск инфраструктуры из `/opt/slouka` после заполнения env:

```bash
docker compose --project-name slouka --env-file production.env \
  -f docker-compose.yaml -f docker-compose.prod.yaml config --quiet
docker compose --project-name slouka --env-file production.env \
  -f docker-compose.yaml -f docker-compose.prod.yaml \
  up -d --no-deps database redis traefik stalwart roundcube
```

Перед первым деплоем дождаться healthy PostgreSQL/Redis и закончить настройку
почты. Все постоянные данные находятся в `var/` на сервере:

| Сервис | Каталог относительно `/opt/slouka` |
| --- | --- |
| PostgreSQL | `var/postgresql` |
| Redis | `var/redis` |
| Traefik (ACME) | `var/traefik/acme` |
| Stalwart (настройки и данные) | `var/stalwart/etc`, `var/stalwart/data` |
| Roundcube | `var/roundcube/db` |

Используются bind mounts: данные доступны напрямую в `/opt/slouka/var/`,
каталог игнорируется Git. Named volumes не используются.

### Конфиги и сертификаты

Файлы `deploy/` хранятся в Git и подключаются в контейнеры только для чтения:

| Файл | Назначение |
| --- | --- |
| `deploy/traefik/routes.yaml` | Маршруты API, веб-почты и HTTP-01 проверки Stalwart |
| `deploy/roundcube/production.php` | HTTPS за прокси, доверие Traefik, проверка сертификатов IMAP/SMTP |
| `deploy/roundcube/resources.conf` | Ограничение числа процессов Apache |
| `deploy/roundcube/resources.ini` | Лимит памяти PHP-запроса 64 МБ |

Параметры подключения Roundcube к почте и `ROUNDCUBEMAIL_DES_KEY` передаются
через `environment` в Compose; PHP-конфиг переменные окружения не читает.

Для API и веб-почты сертификаты Let's Encrypt получает и продлевает Traefik
через TLS-ALPN-01 на порту 443; состояние хранится в `var/traefik/acme`.
Сертификат `mail.slouka.csmmark.me` для SMTP/IMAP получает и продлевает Stalwart
после ручной настройки ACME HTTP-01. Traefik передаёт ему только запросы
`/.well-known/acme-challenge/` на порту 80. Сертификаты Stalwart сохраняются
в его хранилище в `var/stalwart/data`; сертификаты Traefik в Stalwart не копируются.

### GitHub Actions и деплой

В GitHub создать environment `production`. Настройки:

| Где | Имя | Значение |
| --- | --- | --- |
| Repository variable | `DEPLOY_ENABLED` | `true` после подготовки сервера; до этого деплой пропускается |
| Environment variable | `PROD_SSH_HOST` | IP или DNS-имя VPS |
| Environment variable | `PROD_SSH_USER` | SSH-пользователь с доступом к Docker |
| Environment variable | `PROD_SSH_PORT` | SSH-порт, по умолчанию 22 |
| Environment secret | `PROD_SSH_PASSWORD` | Пароль SSH-пользователя |

Actions должны иметь право публикации GHCR package. Для публикации workflow
использует встроенный `GITHUB_TOKEN` с `packages: write`.

PR в `main` запускает `Checks`: Ruff, проверку форматирования, Mypy и pytest.
Push в `main` или ручной запуск workflow на `main` после проверок собирает target
`prod` и публикует `ghcr.io/sloukaapp/backend:<SHA коммита>`. При включённом
`DEPLOY_ENABLED` следующая джоба подключается через `appleboy/ssh-action` по паролю
и передаёт точную ссылку на образ по digest.

На сервере последовательно выполняются скачивание образа, одноразовый migrator
(`alembic upgrade head`) и обновление только backend с ожиданием healthcheck.
Затем проверяется HTTPS OpenAPI. Ошибка останавливает деплой; автоматического
отката нет. Инфраструктура не пересоздаётся, архивы и каталоги релизов не используются.
Значение `BACKEND_IMAGE` в `production.env` пайплайн не переписывает: при ручных
командах указывайте нужный образ самостоятельно.

## API и правила модулей

Контракты запросов, ответов и ошибок доступны в [Swagger](http://localhost:8000/api/v1/docs)
и [OpenAPI](http://localhost:8000/api/v1/openapi.json).
Правила разработки: [общие](AGENTS.md), [auth](src/modules/auth/AGENTS.md),
[users](src/modules/users/AGENTS.md), [decks](src/modules/decks/AGENTS.md),
[practice](src/modules/practice/AGENTS.md).

## Проверки

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest
```

В CI отсутствие собранных тестов пока допускается с предупреждением.
