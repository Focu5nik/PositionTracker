# PositionTracker

Трекер позиций филиалов в локальной поисковой выдаче. Демо Coffee Demo охватывает три филиала, два поисковых запроса и сетку 5×5 на филиал. Один запуск даёт 150 проверок на синтетической платформе `fake_maps`.

Версия **v0.2** добавляет в Django каталог филиалов с доступом по членству в tenant.

## Локальный запуск

Понадобится Docker с плагином Compose и Linux-контейнерами. Из корня проекта в PowerShell выполни:

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
docker compose exec -T monolith python -m apps.monolith.manage migrate
```

Копируй `.env.example` только при первом запуске. Значения в нём предназначены для локальной разработки. Базы и учётные данные RabbitMQ инициализируются при первом запуске с пустыми томами. Имеющиеся данные сохраняются при `docker compose down`.

| Сервис | Имя в сети Compose | Адрес с хоста |
|---|---|---|
| Django | `monolith:8000` | `http://localhost:8000` |
| FastAPI | `tracker:8000` | `http://localhost:8001` |
| PostgreSQL | `postgres:5432` | — |
| RabbitMQ | `rabbitmq:5672` | `http://localhost:15672` для веб-интерфейса |

Для входа в RabbitMQ используй `RABBITMQ_USER` и `RABBITMQ_PASSWORD` из `.env`. Имя базы и роль Django задаются через `MONOLITH_DB_NAME` и `MONOLITH_DB_USER`, FastAPI — через `TRACKER_DB_NAME` и `TRACKER_DB_USER`. Compose передаёт эти параметры приложениям и SQL инициализации PostgreSQL. `migrate` применяет встроенные Django-миграции и создаёт четыре таблицы каталога в базе монолита. Откат через `python -m apps.monolith.manage migrate catalog zero` удаляет таблицы каталога и их данные. Для проверки отката используй отдельную тестовую БД.

Если `.env` создан ранее, добавь в него четыре параметра имён из `.env.example`. Для существующего тома укажи имена уже созданных баз и ролей. Изменение имён в `.env` применяется при инициализации пустого кластера. Для переименования существующих баз и ролей сначала выполни `ALTER DATABASE ... RENAME TO ...` и `ALTER ROLE ... RENAME TO ...` при остановленных приложениях, затем обнови `.env` и пересоздай контейнеры. После переименования роли проверь её пароль, поскольку PostgreSQL сбрасывает MD5-пароль при смене имени роли.

Проверь оба приложения. `/health/live` проверяет HTTP-процесс, `/health/ready` — возможность выполнить `SELECT 1` в своей БД. При недоступной БД `/health/ready` возвращает `503`.

```powershell
curl.exe --fail --silent --show-error http://localhost:8000/health/live
curl.exe --fail --silent --show-error http://localhost:8000/health/ready
curl.exe --fail --silent --show-error http://localhost:8001/health/live
curl.exe --fail --silent --show-error http://localhost:8001/health/ready
```

## Демо-данные и админка

После `migrate` создай данные Coffee Demo и отдельного администратора Django.

```powershell
docker compose exec monolith python -m apps.monolith.manage seed_demo
docker compose exec monolith python -m apps.monolith.manage createsuperuser
```

`seed_demo` запросит пароли для `demo-owner` и `demo-viewer` и выведет ID компании. Команда создаёт один tenant, одну компанию и два филиала. Повторный запуск на готовом наборе сохраняет учётные записи и пароли. Для запуска без терминала передай в окружение контейнера `DEMO_OWNER_PASSWORD` и `DEMO_VIEWER_PASSWORD`.

Админка доступна на [localhost:8000/admin/](http://localhost:8000/admin/). Для входа используй администратора, созданного через `createsuperuser`. Демо-пользователи имеют доступ к каталогу через API. Админка использует права сотрудников Django на модели.

## Чтение филиалов в браузере

1. Открой `http://localhost:8000/api/v1/companies/<id>/locations`, подставив ID компании из `seed_demo`.
2. Нажми **Log in** справа сверху. Войди как `demo-owner` или `demo-viewer`. DRF вернёт тебя на страницу списка и покажет HTTP-статус и тело ответа.
3. Возьми `id` из списка и открой `http://localhost:8000/api/v1/locations/<id>`. Для JSON добавь `?format=json`. Для выхода нажми на имя пользователя и выбери **Log out**. Используй окно инкогнито, чтобы проверить API с отдельной от админки сессией.

## Чтение филиалов из PowerShell

`GET /api/v1/auth/csrf` устанавливает cookie `csrftoken` и возвращает `csrfToken`. `POST /api/v1/auth/login` принимает JSON с `username` и `password`, CSRF-cookie и заголовок `X-CSRFToken`. При успешном входе сервер устанавливает `sessionid` и возвращает новый CSRF-токен. `POST /api/v1/auth/logout` с этим токеном завершает сессию и возвращает `204`.

В примере PowerShell запросит пароль интерактивно. Подставь ID компании из вывода `seed_demo`.

```powershell
$base = 'http://localhost:8000'
$companyId = Read-Host 'Company ID from seed_demo'
$csrf = Invoke-RestMethod "$base/api/v1/auth/csrf" -SessionVariable positionSession
$credentials = Get-Credential -UserName 'demo-owner' -Message 'Coffee Demo'
$login = Invoke-RestMethod "$base/api/v1/auth/login" -Method Post -WebSession $positionSession `
    -ContentType 'application/json' -Headers @{ 'X-CSRFToken' = $csrf.csrfToken } `
    -Body (@{ username = $credentials.UserName; password = $credentials.GetNetworkCredential().Password } | ConvertTo-Json)
Invoke-RestMethod "$base/api/v1/companies/$companyId/locations" -WebSession $positionSession
Invoke-RestMethod "$base/api/v1/auth/logout" -Method Post -WebSession $positionSession `
    -Headers @{ 'X-CSRFToken' = $login.csrfToken }
```

Без сессии каталог возвращает `403`. С сессией запрос `GET /api/v1/locations/{id}` возвращает `404` для чужого или отсутствующего филиала. Список для чужой, отсутствующей или пустой компании возвращает `200` и `[]`.

## Команды разработки

| Make | Эквивалент для PowerShell |
|---|---|
| `make up` | `docker compose up --build --wait` |
| `make down` | `docker compose down` |
| `make logs` | `docker compose logs --tail=100` |
| `make migrate` | `docker compose exec -T monolith python -m apps.monolith.manage migrate` |
| `make test` | `docker compose run --build --rm -T --no-deps monolith python -m pytest` |
| `make lint` | `docker compose run --build --rm -T --no-deps monolith ruff check apps tests` и `docker compose run --rm -T --no-deps monolith mypy` |
| `make smoke` | `docker compose exec -T -e RUN_COMPOSE_TESTS=1 monolith python -m pytest tests/test_compose.py` и `docker compose exec -T -e RUN_COMPOSE_TESTS=1 tracker python -m pytest tests/test_compose.py` |

`make test` проверяет HTTP-контракты и изоляцию каталога на SQLite в памяти. `make smoke` требует запущенные сервисы и проверяет сетевые имена, доступ к своей БД и запрет подключения к чужой, а также интерфейс RabbitMQ.

В WSL с Windows Docker CLI можно передать `DOCKER=docker.exe`, например `make DOCKER=docker.exe up`.

## Материалы проекта

- [Спецификация](docs/product-spec.md) содержит сценарий, Mermaid-диаграммы, правила ранжирования и критерии приёмки.
- [Архитектурные решения](docs/adr/) описывают границы Django и FastAPI, источник отчётов и доставку команд.
- [Филиалы](fixtures/companies.json) и [эталонные выдачи](fixtures/fake_provider_results.json) задают входы и ожидаемые метрики.
- [История изменений](CHANGELOG.md).
