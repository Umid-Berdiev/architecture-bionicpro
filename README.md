# architecture-bionicpro

Проектная работа 9-го спринта курса «Архитектор программного обеспечения» (Яндекс Практикум): кейс BionicPRO —
безопасность SSO, отчёты о работе протезов, локальное хранение данных.

Репозиторий основан на шаблоне [Yandex-Practicum/architecture-bionicpro](https://github.com/Yandex-Practicum/architecture-bionicpro)
(Keycloak + React-фронтенд из уроков).

## Задания

| Задание | Содержание | Где |
|---|---|---|
| 1 | Архитектура управления учётными данными (C4 to-be, BFF, контуры по странам) и переход фронтенда на PKCE | [Task1/README.md](Task1/README.md) |
| 2 | Сервис отчётов: ETL на Airflow (CRM + телеметрия → ClickHouse), витрина, API `/reports` с доступом только к своим данным, UI | [Task2/README.md](Task2/README.md) |

## Запуск

```bash
docker compose up -d --build
docker compose exec airflow-scheduler airflow dags unpause bionicpro_reports_etl
docker compose exec airflow-scheduler airflow dags trigger bionicpro_reports_etl   # первая сборка витрины
```

- Keycloak: http://localhost:8080 (admin / admin), realm `reports-realm`
- Фронтенд: http://localhost:3000 (тестовые пользователи — в `keycloak/realm-export.json`, пилоты протезов: `prothetic1..3`)
- Reports API: http://localhost:8000/reports (Bearer JWT), http://localhost:8000/docs
- Airflow: http://localhost:8081 (admin / admin), DAG `bionicpro_reports_etl`
- ClickHouse: http://localhost:8123 (reports / reports), база `reports`

Тесты:

```bash
docker compose run --rm reports-api python -m pytest -q
docker compose exec airflow-scheduler python -m pytest /opt/airflow/tests -q
```

Realm импортируется только в пустую БД Keycloak; после правок `keycloak/realm-export.json` удалите
`postgres-keycloak-data` и запустите стек заново.

## Диаграммы

Диаграммы draw.io генерируются скриптами из `tools/diagram/` (см. `tools/diagram/README.md`).
