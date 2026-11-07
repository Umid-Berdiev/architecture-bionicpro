# Задание 2. Разработка сервиса отчётов

Файлы:

- `BionicPRO_C4_container-diagram_to-be.drawio` — диаграмма draw.io, две страницы:
  «C4 Container (to-be)» — контейнерная диаграмма из задания 1, дополненная конвейером отчётности;
  «ETL и витрина» — задачи DAG, таблицы ClickHouse и путь чтения отчёта.
- `BionicPRO_C4_container-diagram_to-be.png`, `BionicPRO_ETL_and_mart.png` — экспорт страниц.
- `screenshots/` — отчёт в UI, отказ пользователю без роли, DAG в Airflow, `api-checks.txt` с ответами API.
- Код — в корне репозитория (см. таблицу ниже).

Диаграмма генерируется `tools/diagram/gen_task2.py` из результата задания 1, поэтому все решения задания 1
(контур доступа по странам, BFF, PKCE) сохранены.

---

## Задача 1. Архитектура подготовки и получения отчётов

### Поток данных

| Шаг | Контейнер | Что делает |
|---|---|---|
| 1 | `CRM DB`, `База данных` (телеметрия) | Источники: клиенты и протезы из CRM; показания чипов протезов (жест, время реакции, шум миосигнала, заряд, ошибки) |
| 2 | `Airflow (ETL)`, DAG `bionicpro_reports_etl`, `@hourly` | Извлекает данные из обоих источников и загружает raw-слой в ClickHouse; пересобирает витрину за дни, в которые пришла новая телеметрия; публикует `processed_until` |
| 3 | `Витрина отчётности (OLAP)` — ClickHouse | raw-слой `crm_customers`, `crm_prostheses`, `telemetry_raw`; витрина `reports_mart`; `etl_watermark` |
| 4 | `API` (`reports-api`) | `GET /reports`: проверяет JWT, берёт пользователя из `sub`, читает витрину одним запросом по первичному ключу, не считает ничего на лету |
| 5 | `Веб-приложение` | Кнопки *Get Report* и *Download CSV*, период, таблица по дням |

Задание требует отдавать отчёт через бэкенд-сервис API из исходной архитектуры, поэтому `/reports` реализован
как эндпоинт контейнера `API`, а не отдельного сервиса. В стенде он называется `reports-api`.

### Почему так

- **OLAP отделена от операционной PostgreSQL.** Это прямой ответ на проблему из кейса: телеметрия росла и «тянула»
  за собой остальные таблицы. Аналитика теперь живёт в ClickHouse, операционная БД отдаёт данные ETL один раз в час
  инкрементально (по `recorded_at`), а не на каждый запрос отчёта.
- **Готовая витрина вместо вычислений на лету.** `reports_mart` хранит уже посчитанные агрегаты с зерном
  «пользователь × протез × день». Запрос API — `SELECT … WHERE idp_user_id = ? AND report_date BETWEEN ? AND ?`,
  это один диапазон первичного ключа `(idp_user_id, report_date, prosthesis_serial)`: данные других пользователей
  физически не читаются, время ответа не зависит от объёма телеметрии.
- **ReplacingMergeTree везде, где есть перезапись.** Повторный запуск DAG или пересборка дня не плодит дубликатов:
  измерения вытесняются по `loaded_at`, витрина — по `built_at`, watermark — по `updated_at`; API читает с `FINAL`.
- **Watermark как контракт между ETL и API.** `etl_watermark.processed_until` = `data_interval_end` последнего
  успешного запуска. API не отдаёт данные позже этой границы, даже если в операционной БД они уже есть.
- **Связь пользователя с данными — через `sub` токена.** В CRM у клиента хранится `idp_user_id`; в экспорте realm
  идентификаторы пользователей зафиксированы, чтобы `sub` не менялся при переимпорте. Никаких логинов или e-mail
  в запросах к витрине нет.

### Стенд (docker-compose)

| Сервис | Роль | Порт |
|---|---|---|
| `crm_db` | эмуляция CRM (PostgreSQL; в проде — Битрикс24/Oracle) — `crm/init.sql` | 5434 |
| `telemetry_db` + `telemetry_simulator` | операционная телеметрия: 30 дней seed-данных + новые показания каждые 10 с | 5435 |
| `clickhouse` | OLAP, схема — `clickhouse/init.sql` | 8123 / 9000 |
| `airflow-webserver`, `airflow-scheduler`, `airflow-init`, `airflow_db` | ETL, DAG — `airflow/dags/bionicpro_reports_etl.py` | 8081 (admin / admin) |
| `reports-api` | FastAPI, `reports-api/app` | 8000 |
| `frontend` | React SPA, `frontend/src/components/ReportPage.tsx` | 3000 |
| `keycloak`, `keycloak_db` | IdP (из задания 1) | 8080 |

---

## Задача 2. Airflow DAG и расписание

DAG `bionicpro_reports_etl` (`airflow/dags/bionicpro_reports_etl.py`), TaskFlow API:

```
extract_crm >> extract_telemetry >> build_mart >> update_watermark
```

| Задача | Что делает |
|---|---|
| `extract_crm` | Полная загрузка `customers` и `prostheses` из CRM в `crm_customers` / `crm_prostheses` (справочники маленькие, инкремент не нужен) |
| `extract_telemetry` | Инкремент: `recorded_at > max(recorded_at)` в `telemetry_raw` **и** `≤ data_interval_end`; вставка пачками по 20 000; в XCom — число строк и диапазон дат |
| `build_mart` | `INSERT … SELECT` в `reports_mart` только за дни `[from_date; to_date]` из XCom: `telemetry_raw ⋈ crm_prostheses FINAL ⋈ crm_customers FINAL`, `GROUP BY idp_user_id, toDate(recorded_at), prosthesis_serial`. При нуле новых строк — пропуск |
| `update_watermark` | `etl_watermark(pipeline='reports_mart', processed_until=data_interval_end, dag_run_id)` |

**Витрина `reports_mart`** — отдельная таблица для сервиса отчётов, в которой телеметрия объединена с данными о
клиентах из CRM и сгруппирована в разрезе клиента:

| Колонка | Смысл |
|---|---|
| `idp_user_id`, `username`, `full_name` | клиент (из CRM) |
| `report_date`, `prosthesis_serial`, `model`, `side` | день и протез |
| `actions_count`, `readings_count`, `active_hours` | активность |
| `avg_reaction_ms`, `p95_reaction_ms`, `max_reaction_ms`, `slow_actions_count` | скорость реакции; «медленные» — дольше целевых 100 мс |
| `avg_noise_level` | качество миосигнала |
| `avg_battery_pct`, `min_battery_pct` | батарея |
| `error_count`, `gestures` (Map) | ошибки актуаторов/BMS, распределение жестов |
| `built_at` | версия строки для ReplacingMergeTree |

`ORDER BY (idp_user_id, report_date, prosthesis_serial)`, `PARTITION BY toYYYYMM(report_date)` — быстрый доступ
«по пользователю за период» и дешёвое удаление старых партиций.

**Расписание.** `schedule="@hourly"`, `catchup=False`, `max_active_runs=1`, `retries=2`. Каждый запуск
обрабатывает данные до `data_interval_end` своего интервала; ручной запуск в Airflow получает последний
завершённый часовой интервал, поэтому ручные и плановые запуски дают согласованный watermark. CRM обновляется тем
же часовым запуском: отдельное суточное расписание для справочника на три таблицы не окупается.

Проверка целостности DAG: `airflow/tests/test_dag.py` (импорт без ошибок, расписание, состав и порядок задач):

```bash
docker compose exec airflow-scheduler python -m pytest /opt/airflow/tests -q
```

---

## Задача 3. Бэкенд API

`reports-api` — Python 3.11, FastAPI (`reports-api/app`):

| Модуль | Ответственность |
|---|---|
| `auth.py` | Bearer JWT: подпись по JWKS Keycloak (кэш), `iss`, `aud = reports-api`, `exp`; роли из `realm_access.roles` |
| `repository.py` | Три запроса к ClickHouse: `processed_until`, клиент по `sub`, строки витрины по `(sub, from, to)` |
| `service.py` | Правило периода относительно watermark, сборка ответа, сводка по готовым агрегатам |
| `main.py` | `GET /reports`, `GET /health`, CSV, CORS, маппинг ошибок |

`GET /reports?from=YYYY-MM-DD&to=YYYY-MM-DD&format=json|csv[&user_id=…]`

- Ответ JSON: `user`, `period {from, to, requested_to, clamped}`, `data_processed_until`, `summary`, `days[]`
  (строки витрины, `partial = true` для дня границы, если ETL прошёл не в конце дня).
- `format=csv` — тот же отчёт файлом (`Content-Disposition: attachment`).
- Без дат — последние 7 обработанных дней.

**Только обработанный период.** `data_processed_until` берётся из `etl_watermark`. Если запрошенный конец позже
границы — период обрезается до неё, в ответе `clamped: true` и `requested_to`; если позже границы начало — `422`
с `data_processed_until`; если витрина ещё не собрана — `503`. Пользователь не может получить данные, которых ещё
нет в OLAP, и видит, до какого момента они есть.

Keycloak: к клиенту `reports-frontend` добавлен audience-mapper, поэтому access-токен содержит `aud: reports-api`
и API отвергает токены, выписанные для других сервисов.

---

## Задача 4. Ограничение доступа

1. Без токена, с неверной подписью, чужим `iss`/`aud` или истёкшим сроком — `401`.
2. Без роли `prothetic_user` — `403` (роль назначена только пилотам протезов).
3. Идентификатор пользователя **всегда** берётся из `sub` токена; параметр `user_id` необязателен и допускается
   только равным `sub`, иначе `403` ещё до обращения к витрине. Администратор исключением не является — отчёт
   доступен только в отношении себя.
4. Запрос к ClickHouse параметризован (`{uid:UUID}`), в `WHERE` всегда стоит `idp_user_id = sub`, поэтому даже
   ошибка в вызывающем коде не приведёт к чтению чужих строк.

Юнит-тесты правил (`reports-api/tests/test_reports.py`, Keycloak и ClickHouse заменены заглушками):

```bash
docker compose run --rm reports-api python -m pytest -q
```

12 тестов: 401 без токена и с неверным токеном; 403 без роли; свой отчёт — 200 и запрос к витрине только по
своему `sub`; чужой `user_id` — 403 и витрина не читается; разные пользователи видят только свои протезы;
обрезка периода по watermark; 422 за необработанный период; 503 без витрины; CSV; правила `resolve_period`.

---

## Задача 5. UI

`frontend/src/components/ReportPage.tsx`: после входа (PKCE из задания 1) — выбор периода, кнопка **Get Report**
(таблица по дням, сводка, отметка `partial`, предупреждение об обрезке периода) и кнопка **Download CSV**.
Перед вызовом токен обновляется (`keycloak.updateToken`), ошибки API (401/403/404/422/503) показываются текстом
из ответа.

---

## Проверка на стенде

```bash
docker compose up -d --build          # ~12 контейнеров
# первый запуск DAG — вручную или дождаться начала часа
docker compose exec airflow-scheduler airflow dags unpause bionicpro_reports_etl
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl
```

Результат на стенде (UTC):

| Проверка | Результат |
|---|---|
| Плановый запуск за интервал 18:00–19:00 | 57 580 строк телеметрии → `telemetry_raw`, 128 строк → `reports_mart` (31 день × 4 протеза), `processed_until = 19:00` |
| Ручной запуск после него | 4 строки (остаток интервала), watermark тот же — ручной запуск получает последний завершённый интервал |
| UI, `prothetic1` | отчёт за 7 дней только по `BP-ARM-2024-0001`, последний день помечен *partial* — `screenshots/01-report-prothetic1.png` |
| UI, `user1` (роль `user`) | «role 'prothetic_user' required», 403 — `screenshots/02-user1-without-role-403.png` |
| Airflow | `Schedule: @hourly`, два успешных запуска — `screenshots/03-airflow-dag-hourly.png` |

Ответы API на токен `prothetic1` (`screenshots/api-checks.txt`):

| Запрос | Ответ |
|---|---|
| без токена | `401 authentication required` |
| мусорный токен | `401 invalid token` |
| `?user_id=<свой sub>&from=2026-11-06` | `200`, 2 дня |
| `?user_id=<sub prothetic2>` | `403 a report is available only for your own account` |
| `?from=2026-11-09&to=2026-11-10` (после границы) | `422 data is processed only until 2026-11-07T19:00:00Z` |
| `?from=2026-11-06&to=2026-11-30` | `200`, `period.to = 2026-11-07`, `clamped = true` |
| `?format=csv` | `200 text/csv`, `Content-Disposition: attachment` |

## Что осталось за рамками стенда

- В продуктиве `reports-api` стоит за BFF из задания 1 и получает токен от него, а не от SPA; контракт API при этом
  не меняется.
- Реальная CRM (Битрикс24/Oracle) подключается тем же `extract_crm` через соответствующий hook; эмуляция нужна
  только потому, что в стенде нет Oracle.
- Для больших объёмов `telemetry_raw` имеет смысл TTL на партиции и выделенный пул Airflow; ClickHouse —
  в кластере с репликацией в контуре страны.
