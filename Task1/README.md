# Задание 1. Повышение безопасности системы

Файлы:

- `BionicPRO_C4_container-diagram_to-be.drawio` — доработанная диаграмма контейнеров BionicPRO (draw.io, нотация C4).
  Страница 1 — «C4 Container (to-be)», страница 2 — «Поток токенов (BFF)», sequence-диаграмма входа, вызова API и выхода.
- `BionicPRO_C4_container-diagram_to-be.png`, `BionicPRO_token-flow_BFF.png` — экспорт обеих страниц.
- `screenshots/` — подтверждение работы PKCE (задача 2).
- Этот документ — пояснение принятых решений.

Диаграмма генерируется скриптом `tools/diagram/gen_task1.py` из as-is диаграммы курса
(`tools/diagram/BionicPRO_C4_model_as-is.drawio.xml`, скачана без изменений). Все элементы as-is сохранены;
контейнеры `API` и `База данных` только сдвинуты вправо, чтобы освободить место. Связи, добавленные в to-be,
выделены красным.

---

## Задача 1. Архитектурное решение для управления учётными данными

### 1. Что было не так в as-is

После уроков аутентификация устроена так: React-приложение (`reports-frontend`) — публичный OIDC-клиент Keycloak,
который сам выполняет Authorization Code Grant через `keycloak-js`, получает access-, refresh- и id-токены и держит их
в памяти браузера. Это даёт сразу несколько путей для атаки, которой компания и подверглась:

| Слабое место as-is | Последствие |
|---|---|
| Токены IdP живут во фронтенде (JS-память, при неосторожности — `localStorage`) | Любая XSS-уязвимость или вредоносная зависимость npm выносит refresh-токен, а с ним — долгоживущий доступ от имени пользователя |
| Публичный клиент без PKCE | Перехваченный `code` (redirect, логи, referer, вредоносное расширение) обменивается на токены кем угодно |
| У клиента `reports-frontend` включён Direct Access Grants (password grant) | Пароль можно подбирать напрямую через `/token`, минуя формы входа, MFA и брокеры |
| Один Keycloak и одна учётная база «на всё», пользователи заведены локально | Нет унификации доступа с корпоративными каталогами, при выходе в другие страны данные пациентов неизбежно окажутся в одной юрисдикции |

Задача 2 закрывает второй пункт точечно (PKCE). Архитектурное решение ниже закрывает остальные и задаёт схему, в которой
PKCE — лишь один из уровней защиты.

### 2. Требования и принятые решения

| Требование | Решение | Элементы на диаграмме |
|---|---|---|
| Унификация доступа через внешний источник учётных записей, расположенный в стране представительства; персональные и медицинские данные не покидают страну | **Один контур доступа на страну.** В каждой стране присутствия разворачивается свой экземпляр Keycloak со своей БД, BFF и хранилищем сессий. Keycloak подключается к местному каталогу учётных записей (LDAP / Active Directory) через *User Federation* **без импорта** пользователей: проверка пароля и чтение атрибутов идут в каталог по LDAPS в момент входа, в БД Keycloak остаются только realm, клиенты, роли, сессии и ссылки на федеративные учётные записи | `Контур страны присутствия: Россия`, `Keycloak (IdP страны)`, `БД Keycloak`, `Каталог учётных записей страны`, `Контур страны присутствия: страна N` |
| Безопасная схема работы с access- и refresh-токенами, исключающая передачу фронтенду токенов, полученных от IdP | **Паттерн BFF (Backend for Frontend).** Единственный OAuth2-клиент — серверный `BFF / Auth Gateway` (confidential client). Он выполняет Authorization Code + PKCE, обменивает `code` на токены по back-channel, хранит токены в Redis и выдаёт браузеру/мобильному приложению только случайный `session id` в cookie `HttpOnly; Secure; SameSite=Strict`. Все вызовы API идут через BFF, который подставляет `Authorization: Bearer <access JWT>` | `BFF / Auth Gateway`, `Хранилище сессий`, связи «Вход и вызовы API», «Проксирование запросов пользователя», страница «Поток токенов (BFF)» |
| Поддержка аутентификации через различные внешние удостоверяющие службы разных стран | **Identity Brokering в Keycloak страны.** Keycloak каждого контура настраивается как брокер к удостоверяющим службам своей страны (ЕСИА в РФ, eIDAS-/BankID-провайдеры в ЕС и т. д.) по OIDC или SAML 2.0. Приложения видят только свой Keycloak: подключение новой страны или нового IdP — это конфигурация контура, а не изменение приложений | `Удостоверяющие службы страны`, связь «Identity Brokering» |

### 3. Контейнеры to-be и их ответственность

**BFF / Auth Gateway** (например, Spring Cloud Gateway + Spring Security OAuth2 Client, либо oauth2-proxy / Node.js).

- Единственный OAuth2/OIDC-клиент контура: `client_id = bff`, confidential, PKCE S256 обязателен.
- Хранит `state`, `nonce`, `code_verifier` на сервере на время входа; после обмена кода хранит токены в Redis под ключом `session id`.
- Клиенту выдаёт только cookie сессии; токены, в том числе id-токен, наружу не отдаёт. Нужные фронтенду сведения
  о пользователе (имя, роли) BFF отдаёт отдельным эндпоинтом `/me` из claims id-токена.
- Проксирует запросы к `API`, подставляя access-токен; сам обновляет его по refresh-токену, когда access истёк.
- Защита от CSRF: `SameSite=Strict` плюс заголовок `X-CSRF-Token` (double-submit cookie) для изменяющих запросов.
- Выход: отзывает refresh-токен в Keycloak (`/logout`), удаляет запись в Redis, гасит cookie.

**Хранилище сессий** (Redis).

- `session id → {access_token, refresh_token, id_token, expires_at}`; TTL записи равен сроку жизни refresh-токена,
  поэтому «забытые» сессии исчезают сами.
- Разворачивается внутри контура страны: токены, а значит и персональные данные в их claims, не покидают страну.

**Keycloak (IdP страны)** и **БД Keycloak** (PostgreSQL).

- Один realm на страну; клиенты: `bff` (confidential), `reports-api` (bearer-only), `shop`, `crm` (SSO сотрудников и покупателей).
- User Federation к местному каталогу: `Import Users = OFF`, `Edit Mode = READ_ONLY`. В БД Keycloak не появляется
  копий учётных записей каталога, что и требуется принципом локального хранения.
- Identity Brokering к удостоверяющим службам страны; при первом входе внешняя учётная запись связывается с ролью
  `prothetic_user` через First Login Flow.
- RBAC: роли `user`, `administrator`, `prothetic_user` попадают в access-токен (claim `realm_access.roles`),
  API проверяет их локально.
- Параметры токенов: access — 5 минут, refresh — 30 минут бездействия с ротацией (`Revoke Refresh Token = ON`,
  `Refresh Token Max Reuse = 0`), SSO Session Max — рабочий день. Короткий access ограничивает ущерб от утечки,
  ротация refresh делает украденный refresh одноразовым.

**API** (resource server).

- Принимает только `Authorization: Bearer <JWT>` от BFF. Проверяет подпись по JWKS Keycloak (кэшируется),
  `iss`, `aud`, `exp`, наличие роли; данные отчётов выбираются по `sub` токена, поэтому пользователь физически не может
  получить данные чужого протеза (это требование третьей бизнес-цели, детали реализации — в задании 2).

**Веб-приложение (личный кабинет)** и **Приложение для донастройки протеза**.

- Не содержат OAuth2-клиента и секретов. Вход — переход на `BFF /login`; дальше работают по cookie сессии.
- Мобильное приложение открывает `BFF /login` в системном браузере (Custom Tabs / ASWebAuthenticationSession),
  BFF возвращает cookie сессии через app-link; токены IdP на устройство не попадают, как и в вебе.

**Каталог учётных записей страны** (LDAP / AD) и **Удостоверяющие службы страны** — внешние по отношению к BionicPRO
системы, физически расположенные в стране контура. Каталог — источник учётных данных сотрудников представительства
(продажи, производство, ML); удостоверяющие службы — способ входа пациентов.

### 4. Схема работы с токенами (страница «Поток токенов (BFF)»)

Инвариант схемы: access-, refresh- и id-токены существуют только между BFF, Redis, Keycloak и API; браузер и мобильное
приложение видят только случайный `session id`.

1. **Вход.** Браузер запрашивает `BFF /login`. BFF генерирует `state`, `nonce`, `code_verifier`, вычисляет
   `code_challenge = BASE64URL(SHA-256(code_verifier))` и перенаправляет браузер на `/authorize` Keycloak с `code_challenge`
   и `code_challenge_method=S256`. Keycloak аутентифицирует пользователя: LDAP bind в местный каталог либо редирект на
   внешний IdP (brokering). Код авторизации возвращается на `BFF /callback`; BFF по back-channel обменивает его на токены,
   предъявив `code_verifier` и `client_secret`. Токены сохраняются в Redis, браузеру ставится cookie `sid`.
   Даже перехваченный `code` бесполезен без `code_verifier` и секрета клиента.
2. **Вызов API.** Браузер шлёт `GET /api/reports` с cookie. BFF достаёт токены из Redis, при необходимости обновляет
   access по refresh (с ротацией), вызывает API с `Bearer`-токеном и возвращает ответ. API проверяет JWT по JWKS и
   фильтрует данные по `sub`.
3. **Выход.** BFF отзывает refresh-токен в Keycloak, удаляет сессию из Redis и гасит cookie.

Что это даёт по сравнению с as-is:

- XSS во фронтенде больше не ведёт к краже токенов — красть нечего, а cookie недоступна скрипту (`HttpOnly`).
- Секрет клиента и `code_verifier` никогда не покидают сервер, поэтому перехват кода авторизации не даёт токенов.
- Срок жизни сессии и отзыв управляются на сервере: при инциденте достаточно очистить Redis или отозвать сессии в Keycloak.

### 5. Локальное хранение данных и выход на новые рынки

- Контур доступа (BFF, Redis, Keycloak, его БД) тиражируется в каждую страну; на диаграмме это `Контур страны
  присутствия: Россия` и заглушка `страна N`. Пользователь попадает в контур своей страны по региональному домену
  (`ru.bionicpro.example`, `eu.bionicpro.example`) — так же, как и к данным своего протеза.
- В каждом контуре свой источник учётных записей и свой набор внешних IdP; между контурами учётные данные не
  синхронизируются. Keycloak не импортирует пользователей каталога, поэтому единственные хранимые в BionicPRO
  авторизационные данные — это сессии и ссылки на федеративные учётные записи, и они лежат в стране.
- Приложения (магазин, CRM, API, веб и мобильное приложение) настраиваются на Keycloak своего контура через стандартный
  OIDC Discovery; код приложений от страны не зависит.
- Отключение Direct Access Grants и обязательный PKCE задаются в конфигурации realm каждого контура одинаково.

### 6. Рассмотренные альтернативы

| Альтернатива | Почему не выбрана |
|---|---|
| Оставить публичный SPA-клиент, добавить только PKCE и хранить токены в памяти | PKCE защищает от перехвата кода, но токены по-прежнему во фронтенде — требование «не передавать фронтенду токены IdP» не выполняется, XSS остаётся критичной |
| Один центральный Keycloak с realm на страну и LDAP-федерацией в каждую страну | Сессии, ссылки на учётные записи и логи аутентификации всех стран оказываются в одной юрисдикции; при сбое центрального IdP не работает ни одна страна |
| Мобильное приложение как самостоятельный PKCE-клиент (AppAuth), токены в Keychain/Keystore | Безопасный и общепринятый вариант, но он передаёт токены IdP клиенту, что прямо запрещено условием; оставлен как запасной для сценариев без BFF (офлайн-режим) |
| Реализовать «BFF» внутри `API` | Смешивает управление сессиями с бизнес-логикой; отдельный шлюз проще масштабировать и переиспользовать для всех клиентов контура |

---

## Задача 2. Переход с Code Grant на PKCE

PKCE (RFC 7636) дополняет Authorization Code Grant одноразовой парой `code_verifier` / `code_challenge`: клиент
отправляет в запрос авторизации хэш `code_challenge = BASE64URL(SHA-256(code_verifier))`, а при обмене кода на токены
предъявляет сам `code_verifier`. Перехваченный код авторизации без verifier бесполезен. В Keycloak PKCE включается на
стороне клиента (раздел *Advanced → Proof Key for Code Exchange Code Challenge Method* в консоли, атрибут
`pkce.code.challenge.method` в экспорте realm), а `keycloak-js` начинает использовать его при `pkceMethod: 'S256'`.

### Что изменено

| Файл | Изменение | Зачем |
|---|---|---|
| `keycloak/realm-export.json`, клиент `reports-frontend` | `"attributes": {"pkce.code.challenge.method": "S256"}` | Keycloak **требует** PKCE от этого клиента: запрос авторизации без `code_challenge` отклоняется, обмен кода без `code_verifier` невозможен. `S256`, а не `plain`: challenge в URL не раскрывает verifier |
| там же | `"directAccessGrantsEnabled": false` | У публичного SPA-клиента не должно быть password grant — это прямой перебор паролей через `/token` в обход форм входа, MFA и брокеров |
| там же | `"standardFlowEnabled": true`, `"implicitFlowEnabled": false`, `post.logout.redirect.uris` | Явно оставлен только Authorization Code flow; implicit flow (токены в URL) запрещён; корректный redirect после logout |
| `frontend/src/App.tsx` | `initOptions={{ pkceMethod: 'S256', onLoad: 'check-sso' }}` у `ReactKeycloakProvider` | `keycloak-js` генерирует `code_verifier`, добавляет `code_challenge`/`code_challenge_method=S256` в запрос авторизации и передаёт verifier в `/token`; `check-sso` восстанавливает сессию без лишнего редиректа на форму входа |

Realm импортируется при старте (`--import-realm`) только в пустую БД, поэтому после изменения экспорта нужно пересоздать
том Keycloak: `docker compose down && rm -rf postgres-keycloak-data && docker compose up -d --build`.

### Проверка

1. **Запрос авторизации из приложения содержит PKCE-параметры.** После нажатия *Login* браузер уходит на
   ```
   http://localhost:8080/realms/reports-realm/protocol/openid-connect/auth?client_id=reports-frontend
     &redirect_uri=http%3A%2F%2Flocalhost%3A3000%2F&state=a4d153ae-…&response_mode=fragment&response_type=code
     &scope=openid&nonce=1b16e21f-…&code_challenge=zTkLic_7QipO2EPv_-27QCBR1MxfhvECaX7fu7_aS5Y&code_challenge_method=S256
   ```
   Вход под `prothetic1` проходит, `POST /protocol/openid-connect/token` отвечает `200`, открывается страница отчётов
   (`screenshots/02-keycloak-login-page.png`, `screenshots/03-report-page-after-login.png`).
2. **Keycloak отклоняет запрос без PKCE.** Тот же запрос авторизации без `code_challenge`:
   ```
   curl -sD - -o /dev/null "http://localhost:8080/realms/reports-realm/protocol/openid-connect/auth?client_id=reports-frontend&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2F&response_type=code&scope=openid&state=abc"
   Location: http://localhost:3000/?error=invalid_request&error_description=Missing+parameter%3A+code_challenge_method&state=abc
   ```
   В логе Keycloak: `AuthorizationEndpointChecker ... PKCE enforced Client without code challenge method.`
3. **Password grant закрыт.**
   ```
   curl -s -X POST http://localhost:8080/realms/reports-realm/protocol/openid-connect/token \
     -d client_id=reports-frontend -d grant_type=password -d username=prothetic1 -d password=prothetic123
   {"error":"unauthorized_client","error_description":"Client not allowed for direct access grants"}
   ```
4. **Настройка клиента в консоли Keycloak** — `screenshots/01-keycloak-client-pkce-s256.png`
   (*Proof Key for Code Exchange Code Challenge Method = S256*).

### Что PKCE не закрывает

PKCE защищает только обмен кода авторизации. Токены по-прежнему оказываются в браузере, поэтому целевой схемой остаётся
BFF из задачи 1: PKCE там выполняет серверный клиент, а фронтенд токенов не видит вовсе.
