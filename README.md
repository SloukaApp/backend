# Slouka backend

Python 3.14, FastAPI, PostgreSQL 17. Работать из `backend/`; импорты начинаются с `src`.

## Команды Make

`make` показывает доступные команды. `make dev-up` / `make prod-up` собирают
образы и запускают окружение в фоне; `make dev-stop` / `make prod-stop`
останавливают контейнеры. `make dev-down` / `make prod-down` также удаляют
контейнеры и сеть, сохраняя данные в `var/`. Дополнительно доступны команды
`dev-build`, `dev-logs`, `dev-ps`, `dev-config` и их варианты с префиксом `prod-`.

Dev и prod используют явные пары Compose-файлов. Это альтернативные режимы
одного стека: имена инфраструктурных контейнеров, сеть и данные общие, поэтому
перед переключением выполните `make dev-down` или `make prod-down` для текущего
режима. Команды `*-up` запускают migrator и применяют миграции.

## Первый запуск

Создайте `.env` по `.env.template` самостоятельно. Задайте собственный случайный
`AUTH__JWT_SECRET` (например, сгенерированный менеджером паролей), параметры PostgreSQL
и SMTP sender. Пример секрета из шаблона непригоден для реального окружения.
Для dev задайте `PGADMIN_DEFAULT_EMAIL` и непустой `PGADMIN_DEFAULT_PASSWORD`;
`PGADMIN_PORT` задаёт порт веб-интерфейса (по умолчанию `5050`).
Юридический текст согласия предоставляет приложение: backend хранит переданную
непустую `consent_version` и время явного согласия, не создаёт юридический текст.

```bash
uv sync
docker compose config --quiet
docker compose build backend migrator
docker compose up -d
```

Сервис приложения называется `backend`. Dev override подключается автоматически.
`database` должен стать healthy, затем `migrator` выполняет `alembic upgrade head`,
и только после его успешного завершения запускается API. На существующей/общей БД
сначала согласуйте применение миграций; `up` применяет их автоматически. Не удаляйте
volumes и не используйте downgrade для обычного запуска.

- API и Swagger: http://localhost:8000/api/v1/docs
- OpenAPI: http://localhost:8000/api/v1/openapi.json
- Mailpit UI: http://localhost:8025
- pgAdmin (только dev): http://localhost:5050, вход по `PGADMIN_DEFAULT_EMAIL`
  и `PGADMIN_DEFAULT_PASSWORD`. Данные интерфейса сохраняются в `var/pgadmin`.
- SMTP с хоста: `localhost:1025` (опубликован dev override).
- PostgreSQL с хоста: `localhost:5432` (опубликован dev override).

В контейнерах PostgreSQL доступен как `database:5432`, SMTP как `mailpit:1025`.
В pgAdmin добавьте сервер с host `database`, port `5432`, maintenance database
из `DB__NAME`, username из `DB__USER` и password из `DB__PASSWORD`.
pgAdmin доступен только через loopback; учётная запись создаётся при первом запуске,
последующее изменение переменных не меняет пароль уже созданной записи.
Compose переопределяет локальный DB DSN и SMTP host; Mailpit работает без TLS и
STARTTLS. Если логин/пароль БД содержит URL-спецсимволы, задайте дополнительно
`DB__CONTAINER_DSN` с URL-encoded credentials и адресом `database:5432` в своём
окружении. Не публикуйте этот DSN и не выводите разрешённую конфигурацию Compose.

Для локального API оставьте в `.env` адреса БД и SMTP `localhost`, поднимите только
инфраструктуру и осознанно примените миграции:

```bash
docker compose up -d --no-deps database mailpit
uv run alembic upgrade head
uv run uvicorn src.main:create_app --factory --no-proxy-headers --reload --host 127.0.0.1 --port 8000
```

Для production используйте явную пару файлов, без автоматического dev override:

```bash
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml config --quiet
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml build backend migrator
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

Перед внешним размещением настройте HTTPS и подходящий SMTP. Текущий Compose
использует Mailpit для разработки; production override сам по себе не заменяет
почтовую инфраструктуру. SMTP имеет timeout 10 секунд и максимум 2 повтора;
`SMTP__USE_TLS` и `SMTP__START_TLS` задаются явно. Подключения закрываются после
каждой попытки, общий адаптер управляется lifespan.

Redis отсутствует в Compose и для users/auth не требуется. Существующий клиент
Redis ленивый, lifespan не выполняет ping. Для будущих возможностей и отдельного
Taskiq worker понадобится отдельно доступный Redis. Ограничение попыток входа
**ещё не реализовано**: сохранены только настройки, окно унифицировано на 900 секунд.

## HTTP сценарии

Все пути ниже относительно `/api/v1`, тела и ответы — JSON. `installation_id` —
стабильный UUID установки мобильного приложения, не секрет и не доказательство
авторизации. Сохраняйте его на устройстве. Для защищённых маршрутов передавайте
`Authorization: Bearer <access_token>`.

1. `POST /auth/register`: `email`, `password` (минимум 8 символов),
   `consent: true`, `consent_version`. Создаёт неподтверждённую запись и возвращает
   201 после отправки письма; access/refresh и confirmation token в ответ не входят.
2. Прочитайте токен из письма в Mailpit. Письмо содержит токен, без ссылки;
   мобильный клиент вызывает `POST /auth/confirm-email` с `email`, `token` и
   `installation_id`. Ответ содержит `access_token`, `refresh_token`,
   `token_type: bearer`, `expires_in: 1800`. GET-подтверждения нет.
3. Для последующих входов: `POST /auth/login` с `email`, `password`,
   `installation_id`. Неподтверждённый email даёт 403.
4. `POST /auth/refresh` требует только `refresh_token`. Сохраните новую пару:
   предыдущий refresh одноразовый, повторное использование даёт 401 и не
   отзывает другие устройства.
5. `GET /auth/devices?limit=50&offset=0` возвращает `{items,total,limit,offset}`;
   записи содержат `active`, включая исторические неактивные установки.
   `DELETE /auth/devices/{device_id}` отзывает свою установку; чужая/отсутствующая — 404.
6. `POST /auth/logout` отзывает refresh устройства из access JWT;
   `POST /auth/logout-everywhere` отзывает все refresh аккаунта.
7. `POST /auth/password`: `current_password`, `new_password`; меняет пароль и
   отзывает все refresh в одной транзакции, новые токены не выдаёт.
8. `GET /users/me`, `PATCH /users/me` (`timezone`, `reminders_enabled`,
   `reminder_time`), `POST /users/me/onboarding`. Onboarding идемпотентен.
   Timezone — IANA; reminder_time — локальное время без offset. Для включения
   напоминаний нужны timezone и время; само расписание доставки в этот этап не входит.
   PATCH применяет только переданные поля; email через профиль не меняется.

Подтверждение действует 15 минут. Код состоит из 6 криптографически случайных
символов `A–Z`, `a–z`, `0–9`; регистр значим. `POST /auth/confirmations/resend` с `email` и
`password` разрешён не чаще раза в 60 секунд и аннулирует предыдущий токен.
Дополнительный лимит resend не введён. Повторная регистрация того же email — 409;
для неподтверждённой записи используйте resend. Если SMTP недоступен, ответ 503
явно сообщает об ошибке доставки: аккаунт/подтверждение уже сохранены. После
cooldown используйте resend, не новую регистрацию. SMTP-повторы не гарантируют
exactly-once доставку; пригоден только последний действующий токен.

Access JWT HS256 живёт 30 минут, refresh — 30 дней; иные TTL отвергаются настройками.
Лимит активных устройств берётся из настроек, минимум 5. Повторный вход той же
установки заменяет её refresh. При превышении лимита — 409 без вытеснения.
Logout/смена пароля не аннулируют уже выданные access JWT: они действуют до exp
при обязательной проверке существования аккаунта на каждом защищённом запросе.
Удаление аккаунта и восстановление забытого пароля не реализованы.

## Архитектура и проверка

`auth → users`: AuthService владеет регистрацией, подтверждением, входом, сменой
пароля и отзывом авторизаций; UsersService владеет аккаунтом и паролями. У модулей
общий operation-scoped UoW. Блокировка строки аккаунта через публичный UsersService
сериализует выдачу устройств, refresh, resend и смену пароля, включая первый вход.
UUIDv7 генерируется Python-default полей ORM при INSERT. Роутеры users и auth —
обычные APIRouter; users подключает auth dependency на HTTP-уровне, сервисы
сохраняют направление зависимости `auth → users`.
Refresh и подтверждения дополнительно блокируются `FOR UPDATE`; в БД только их
SHA-256 хеши. Пароли — Argon2. Уникальности и частичные индексы обеспечиваются БД.

Роутеры управляют транзакциями; проверка access dependency завершается отдельной
последовательной стадией перед контекстом endpoint. Права/аккаунт проверяются
повторно в операции. SMTP выполняется после commit, вне транзакции. ORM users не
доступен auth. Миграция `20261022_01` создаёт users/devices/refresh_tokens/
email_confirmations; mappings явно зарегистрированы в Alembic env.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
```

Тесты и проверочный цикл миграций на этом этапе не запускаются по согласованному
объёму. Для диагностики запуска используйте `docker compose ps`; не публикуйте
секреты, токены, тела писем или персональные данные из логов/API.

## Rate limiting

Проверки подключены через FastAPI Depends, без rate-limit middleware.
Sliding window counter использует оценку `current + previous * (1 - elapsed / window)`:
это приблизительный бюджет, а не гарантия N попыток за любой скользящий интервал.
См. [описание алгоритма Redis](https://redis.io/tutorials/howtos/ratelimiting/#3-sliding-window-counter).

| Операция | Субъект | Предел | Окно | Учёт |
| --- | --- | --- | --- | --- |
| confirm-email | нормализованный введённый email | 5 | 900 с | все допущенные проверки |
| confirm-email | IP | 20 | 900 с | все допущенные проверки |
| login | IP | 60 | 60 с | все допущенные проверки |
| login | аккаунт–IP | 10 | 900 с | все допущенные проверки |

Оба бюджета каждой операции проверяются и расходуются вместе атомарно в Lua
через Depends до открытия транзакции БД. Сервис auth не участвует в rate limiting.
Несуществующий email тоже расходует бюджет подтверждения. Resend его не сбрасывает.
Код проверяется только для введённого email; отсутствующий аккаунт, чужой,
неверный, использованный, отозванный или истёкший код дают одинаковый 401.
Субъект бюджета login — нормализованный введённый email в паре с IP;
несуществующий аккаунт тоже расходует оба бюджета и получает 401.
Успешные входы расходуют оба бюджета и не сбрасывают их.
Исчерпание любого бюджета блокирует и правильный пароль до следующего допуска.
Refresh бюджеты login не расходует. Общих лимитов auth/users нет;
дополнительных бюджетов регистрации и resend нет.

429 возвращает ErrorResponse и целочисленный Retry-After (округление вверх,
минимум 1 с), рассчитанный по спаду оценки обоих интервалов, включая переход
границы окна. Другие запросы могут потратить бюджет за время ожидания.
Отказ по любому бюджету не увеличивает ни один счётчик операции
и не продлевает их TTL.
Сбой Redis даёт 503 на login/confirm-email; остальные операции не проверяют Redis.
Состояние счётчиков не откатывается с транзакцией PostgreSQL.

Источник времени — Redis TIME внутри Lua. Один hash на бюджет хранит номер
интервала, текущий и предыдущий счётчики; TTL — два окна после последнего
увеличения. Все ключи имеют общий hash tag `{rate_limit}` для атомарной проверки
двух бюджетов в Redis Cluster. Используется REDIS__KEY_PREFIX.
По согласованному решению ключи содержат открытые нормализованные email и IP;
отдельного HMAC-секрета нет. Пароли и коды в ключи и логи не попадают.

Compose запускает Redis 7.4, AOF everysec, named volume redis_data, без порта
на хосте; backend использует redis://redis:6379/0. При рестарте AOF восстанавливает
бюджеты, но последние записи могут потеряться. Для backend вне Compose нужен
отдельно доступный Redis по REDIS__DSN.

IP берётся из request.client после единственного ProxyHeadersMiddleware Uvicorn
в приложении ([исходный код Uvicorn](https://github.com/encode/uvicorn/blob/main/uvicorn/middleware/proxy_headers.py)). Доверенные прокси задаёт APP__TRUSTED_PROXIES (по умолчанию []);
Docker и приведённая команда запуска отключают внешнюю обработку заголовков
через --no-proxy-headers. При другом запуске сохраняйте этот параметр, чтобы
не включить дополнительный слой доверия forwarded-заголовкам.
