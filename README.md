# bondelo-backend


## Структура

```
app/
  core/        конфиг, логирование, контекст запроса, доменные ошибки
  db/          declarative Base, async engine и сессии
  api/         HTTP-слой: роутеры и зависимости
  users/       пользователи бота: единственная таблица, которой владеет сервис
  portfolio/   вертикальный срез фичи: модели, схемы, запросы, бизнес-логика
migrations/    Alembic: схема `bot_users`
tests/         pytest поверх настоящего Postgres
```

Границы слоёв: `api/v1/*` работает только со схемами и сервисом; `service` не знает про HTTP и бросает ошибки из `core/exceptions.py`; `repository` содержит только запросы. Новая фича добавляется как новый пакет по образцу `portfolio/`.



## Локальный запуск

```bash
uv sync
cp .env.example .env     
uv run fastapi dev app/main.py
```

Документация — http://localhost:8000/docs.

Проверки: `uv run ruff format . && uv run ruff check . && uv run basedpyright`.

Тесты (нужен Postgres из `docker-compose.test.yml`):

```bash
docker compose -f docker-compose.test.yml up -d
uv run pytest
```

Тесты сами накатывают миграции на тестовую БД. Адрес по умолчанию —
`postgresql+asyncpg://postgres:postgres@localhost:5433/bondelo_test`, переопределяется
переменной `TEST_DATABASE_URL`. Postgres здесь обязателен: запросы используют
`ON CONFLICT`, `xmax` и `json_agg`.

## Миграции

Схемой таблицы `bot_users` владеет этот сервис — она заводится и меняется только
через Alembic отсюда. Все остальные таблицы (`user_bonds`, `moex_bonds`,
`moex_bonds_offers`, а также таблицы бота и мониторингов) принадлежат другим
сервисам: модели для них read-only, и autogenerate их не видит — в `migrations/env.py`
стоит белый список `OWNED_TABLES`. **Добавляя свою таблицу, впишите её туда**, иначе
миграция для неё не сгенерируется.

```bash
uv run alembic revision --autogenerate -m "что меняем"
uv run alembic upgrade head
uv run alembic check      # расхождений моделей и БД быть не должно
```

Версии пишутся в `alembic_version_bondelo_api`, а не в общий `alembic_version`: базу
делят несколько сервисов.

В уже существующей базе (прод) первая ревизия не применяется — таблица там давно
есть, её создавал `create_all` бота. Такую БД нужно один раз пометить:

```bash
DATABASE_URL=<прямое подключение, порт 5432> uv run alembic stamp head
```

Именно прямое подключение, не пулер: asyncpg с pgbouncer в transaction mode ломается
на prepared statements. Одно отличие от прода останется историческим: первичный ключ
там называется `bot_users_pkey`, а в моделях — `pk_bot_users` (naming convention из
`app/db/base.py`). На работу это не влияет, но миграция, которая трогает PK, должна
знать про оба имени.

## Эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | liveness, без обращения к БД |
| GET | `/health/ready` | readiness, делает `SELECT 1` |
| POST | `/api/v1/users/register` | регистрация пользователя бота (идемпотентно) |
| GET | `/api/v1/users/active` | telegram_id всех активных пользователей |
| GET | `/api/v1/users/{telegram_id}/token` | токен T-Invest пользователя |
| PUT | `/api/v1/users/{telegram_id}/token` | сохранить токен T-Invest |
| DELETE | `/api/v1/users/{telegram_id}/token` | отвязать токен |
| POST | `/api/v1/users/{telegram_id}/deactivate` | пометить пользователя неактивным |
| GET | `/api/v1/users/{telegram_id}/offers?limit=5` | N ближайших оферт по портфелю пользователя |
| GET | `/api/v1/users/{telegram_id}/maturities?limit=5` | N ближайших погашений по портфелю пользователя |

### Пользователи

`POST /api/v1/users/register` — тело `{"telegram_id": 1, "username": null, "first_name":
null, "last_name": null}`, ответ `{"telegram_id": 1, "is_new_user": true, "has_token":
false}`. Одним `INSERT ... ON CONFLICT`, поэтому параллельные `/start` не создают дублей;
повторный вызов обновляет `last_activity` и снимает деактивацию. `is_new_user`
отличает первый `/start` от повторного, `has_token` — подключён ли T-Invest.

Ручки токена и деактивации отвечают `404`, если пользователь неизвестен. Пустая строка
в `tinvest_token` (так его снимали раньше) считается отсутствием токена.

Токен ходит по сети только внутри приватного Cloud Run и только в теле запроса —
в URL, query и логи он не попадает.

### Портфель

Общее для `offers` и `maturities`:

- `limit` — сколько ближайших событий вернуть (1–50, по умолчанию 5).
- Портфель стыкуется с бумагами MOEX по ISIN; позиции без ISIN игнорируются.
- Количество агрегируется по всем брокерам и счетам, состав счетов — в `accounts`.
- Неизвестный `telegram_id` → `404`; известный пользователь без подходящих событий → `200` и пустой `items`.

`GET /api/v1/users/{telegram_id}/offers`

- Возвращает оферты с `offerdate >= сегодня`, отсортированные по дате; отменённые (`offertype` содержит «отменено») исключены. У одной бумаги может быть несколько оферт в выдаче.

`GET /api/v1/users/{telegram_id}/maturities`

- Возвращает бумаги с `matdate >= сегодня`, отсортированные по дате погашения — по одной строке на бумагу. Вместо блока `offer` приходит `maturity`:

```json
{
  "bond": {"secid": "RU000A10AU73", "isin": "RU000A10AU73", "shortname": "ГТЛК 2P-07",
           "name": "ГТЛК БО 002P-07", "facevalue": "1000", "faceunit": "SUR",
           "matdate": "2026-08-04"},
  "maturity": {"date": "2026-08-04", "days_left": 9},
  "quantity": "80.0000",
  "accounts": [{"broker": "tbank", "account_id": "2045796893",
                "account_name": "ИИСус", "quantity": "40.0000"}]
}
```

```json
{
  "telegram_id": 1825344258,
  "items": [
    {
      "bond": {"secid": "RU000A10AS28", "isin": "RU000A10AS28", "shortname": "БинФарм1P4",
               "name": "...", "facevalue": "1000", "faceunit": "SUR", "matdate": "2028-01-20"},
      "offer": {"date": "2026-08-05", "type": "Оферта", "date_start": null, "date_end": null,
                "price": "100", "value": null, "agent": null, "days_left": 11},
      "quantity": "44.0000",
      "accounts": [{"broker": "tinkoff", "account_id": "...", "account_name": "ИИС",
                    "quantity": "24.0000"}]
    }
  ]
}
```

Денежные величины и количества сериализуются строками — чтобы не терять точность `Decimal`.

## Деплой в Cloud Run

Авторизация — **только IAM**, кода проверки токенов в сервисе нет: Cloud Run валидирует ID-token до того, как запрос дойдёт до контейнера.

```bash
gcloud run deploy bondelo-api \
  --source . \
  --no-allow-unauthenticated \
  --set-secrets DATABASE_URL=bondelo-database-url:latest \
  --set-env-vars APP_ENV=prod

gcloud run services add-iam-policy-binding bondelo-api \
  --member=serviceAccount:bondelo-bot@PROJECT.iam.gserviceaccount.com \
  --role=roles/run.invoker
```

Миграции контейнер не накатывает — `alembic upgrade head` гоняется отдельно,
перед деплоем, по прямому подключению к БД (см. «Миграции»).

Бот получает токен из metadata server и шлёт его в заголовке:

```
GET http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=<API_URL>
Metadata-Flavor: Google

→ Authorization: Bearer <id-token>
```

Ручная проверка прод-URL: `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" <API_URL>/health`.

Контейнер слушает `$PORT` (по умолчанию 8080) — его задаёт Cloud Run. Логи в проде пишутся JSON-ом с полями `severity`/`message` и `trace_id` из `X-Cloud-Trace-Context`, поэтому в Cloud Logging запросы бота и API сшиваются в одну трассу.
