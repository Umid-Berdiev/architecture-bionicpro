# architecture-bionicpro

Проектная работа 9-го спринта курса «Архитектор программного обеспечения» (Яндекс Практикум): кейс BionicPRO —
безопасность SSO, отчёты о работе протезов, локальное хранение данных.

Репозиторий основан на шаблоне [Yandex-Practicum/architecture-bionicpro](https://github.com/Yandex-Practicum/architecture-bionicpro)
(Keycloak + React-фронтенд из уроков).

## Задания

| Задание | Содержание | Где |
|---|---|---|
| 1 | Архитектура управления учётными данными (C4 to-be, BFF, контуры по странам) и переход фронтенда на PKCE | [Task1/README.md](Task1/README.md) |

## Запуск

```bash
docker compose up -d --build
```

- Keycloak: http://localhost:8080 (admin / admin), realm `reports-realm`
- Фронтенд: http://localhost:3000 (тестовые пользователи — в `keycloak/realm-export.json`)

Realm импортируется только в пустую БД Keycloak; после правок `keycloak/realm-export.json` удалите
`postgres-keycloak-data` и запустите стек заново.

## Диаграммы

Диаграммы draw.io генерируются скриптами из `tools/diagram/` (см. `tools/diagram/README.md`).
