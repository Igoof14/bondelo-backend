# bondelo-backend


## Структура

```
app/
  core/        конфиг, логирование, контекст запроса, доменные ошибки
  db/          declarative Base, async engine и сессии
  api/         HTTP-слой: роутеры и зависимости
  portfolio/   вертикальный срез фичи: модели, схемы, запросы, бизнес-логика
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

## Эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | liveness, без обращения к БД |
| GET | `/health/ready` | readiness, делает `SELECT 1` |
| GET | `/api/v1/users/{telegram_id}/offers?limit=5` | N ближайших оферт по портфелю пользователя |

`GET /api/v1/users/{telegram_id}/offers`

- `limit` — сколько ближайших оферт вернуть (1–50, по умолчанию 5).
- Портфель стыкуется с бумагами MOEX по ISIN; позиции без ISIN игнорируются.
- Возвращаются оферты с `offerdate >= сегодня`, отсортированные по дате; отменённые (`offertype` содержит «отменено») исключены. У одной бумаги может быть несколько оферт в выдаче.
- Количество агрегируется по всем брокерам и счетам, состав счетов — в `accounts`.
- Неизвестный `telegram_id` → `404`; известный пользователь без позиций → `200` и пустой `items`.

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

Бот получает токен из metadata server и шлёт его в заголовке:

```
GET http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=<API_URL>
Metadata-Flavor: Google

→ Authorization: Bearer <id-token>
```

Ручная проверка прод-URL: `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" <API_URL>/health`.

Контейнер слушает `$PORT` (по умолчанию 8080) — его задаёт Cloud Run. Логи в проде пишутся JSON-ом с полями `severity`/`message` и `trace_id` из `X-Cloud-Trace-Context`, поэтому в Cloud Logging запросы бота и API сшиваются в одну трассу.
