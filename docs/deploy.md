# Развёртывание первой версии в контуре

Первая версия работает без Keycloak (`AUTH_DISABLED=true`, решение D-41) и без доступа в
интернет: скрипты, стили и HTMX отдаются из самого образа. Внешний Postgres и шлюз модели ВСК
в контуре уже есть.

## Что нужно заранее

- реестр образов, доступный кластеру, и права на `docker push`;
- namespace `cargo-assistant` (создаёт `deploy/k8s/namespace.yaml`);
- StorageClass с режимом `ReadWriteMany` для общего хранилища файлов;
- база Postgres 14+ и пользователь с правом создавать таблицы; адрес в формате
  `postgresql+asyncpg://пользователь:пароль@хост:5432/база`;
- адрес шлюза модели (OpenAI-совместимый `/v1/chat/completions`), ключ и имя модели;
- корневой сертификат корпоративного CA, если шлюз подписан им.

## Шаги

1. **Собрать образ.** Версия — короткий хэш коммита, он же тег; для рабочей копии с
   несохранёнными изменениями добавляется `-dirty`.

   ```bash
   deploy/build-image.sh registry.example.local/cargo-assistant
   docker push registry.example.local/cargo-assistant:<хэш>
   ```

2. **Проверить, что в образе нет документов клиента.**

   ```bash
   docker run --rm --entrypoint sh registry.example.local/cargo-assistant:<хэш> -c \
     'find / -xdev \( -name "*.xls*" -o -name "*.doc*" -o -name "*.zip" -o -name ".env*" \) \
      -not -path "/usr/*" -not -path "/proc/*"'
   ```

   Вывод должен быть пустым (допустим только `/.dockerenv`). В образ попадают `app/`,
   `migrations/`, `cards/`, `alembic.ini`, `pyproject.toml`.

3. **Подставить образ и адреса в манифесты `deploy/k8s/`:**
   - `registry.example.invalid/cargo-assistant:replace-with-tag` в `api.yaml`, `worker.yaml`,
     `migrate.yaml` — на собранный образ;
   - `storageClassName: replace-with-rwx-class` в `storage.yaml`;
   - `host` и `ingressClassName: replace-with-class` в `api.yaml` (Ingress);
   - в `config.yaml` — `LLM_API_URL`, `LLM_MODEL` и при необходимости `LLM_CA_BUNDLE`
     (см. «Сертификат шлюза»).

4. **Создать namespace, секрет и конфигурацию.**

   ```bash
   kubectl apply -f deploy/k8s/namespace.yaml
   kubectl -n cargo-assistant create secret generic cargo-secret \
     --from-literal=DATABASE_URL='postgresql+asyncpg://пользователь:пароль@хост:5432/база' \
     --from-literal=LLM_API_KEY='ключ шлюза'
   kubectl apply -f deploy/k8s/config.yaml -f deploy/k8s/storage.yaml
   ```

   `deploy/k8s/secret.example.yaml` — только шаблон без значений; файл с настоящими значениями
   (`deploy/k8s/secret.yaml`) в git не попадает.

5. **Применить миграции до старта сервисов.** Миграции идут отдельным заданием, чтобы две
   реплики не меняли схему одновременно.

   ```bash
   kubectl -n cargo-assistant delete job cargo-migrate --ignore-not-found
   kubectl apply -f deploy/k8s/migrate.yaml
   kubectl -n cargo-assistant wait --for=condition=complete job/cargo-migrate --timeout=300s
   ```

6. **Запустить сервисы.**

   ```bash
   kubectl apply -f deploy/k8s/api.yaml -f deploy/k8s/worker.yaml
   kubectl -n cargo-assistant rollout status deploy/cargo-api deploy/cargo-worker
   ```

## Проверка

```bash
kubectl -n cargo-assistant exec deploy/cargo-api -- python -m app.llm probe
kubectl -n cargo-assistant port-forward svc/cargo-api 8080:80
curl -i http://localhost:8080/health
```

- `/health` отвечает 200; страницы `/policies`, `/reconcile`, `/archive` открываются;
- `python -m app.llm probe` печатает замеры шлюза; по его итогам выбирают
  `LLM_RESPONSE_FORMAT` (`prompt`, `json_object`, `json_schema`, `guided_json`);
- в логе api при старте есть строка «Вход отключён, сервис доступен без проверки пользователя»,
  на каждой странице сверху красная пометка «вход отключён»;
- в логе воркера есть строка «Воркер запущен».

## Переменные окружения

Секреты (`cargo-secret`): `DATABASE_URL`, `LLM_API_KEY`, `SESSION_SECRET`, `KEYCLOAK_CLIENT_SECRET` (последние два нужны при включённом входе). Остальное — ConfigMap `cargo-config`.

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `DATABASE_URL` | адрес Postgres (секрет) | — |
| `STORAGE_DIR` | каталог общего хранилища, смонтированный PVC | `/data/storage` |
| `AUTH_DISABLED` | `true` — вход без Keycloak, пометка на страницах и предупреждение в логе | `false` |
| `AUTH_DEV_USER_ID` | идентификатор единственного пользователя при `AUTH_DISABLED=true`; имя — «Локальный пользователь» | `dev-user` |
| `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID` | адрес Keycloak, реалм и клиент (authorization code flow с PKCE); redirect URI клиента — `<адрес сервиса>/auth/callback` | — |
| `KEYCLOAK_CLIENT_SECRET` | секрет клиента, если он конфиденциальный (секрет) | пусто |
| `SESSION_SECRET` | ключ подписи cookie сессии; без него при `AUTH_DISABLED=false` сервис не стартует (секрет, одинаков во всех подах api) | — |
| `SESSION_SECURE` | cookie только по HTTPS; `false` — лишь для http без TLS | `true` |
| `SESSION_HOURS` | срок сессии в часах; по истечении снова вход | `12` |
| `APP_BASE_URL` | внешний адрес для redirect_uri, если за прокси схема или хост определяются неверно | пусто |
| `FORWARDED_ALLOW_IPS` | адреса, которым uvicorn верит в `X-Forwarded-*` (адрес ingress или `*`) | `127.0.0.1` |
| `LLM_PROVIDER` | `vsk` — шлюз ВСК | `vsk` |
| `LLM_API_URL`, `LLM_MODEL` | адрес и модель шлюза | — |
| `LLM_API_KEY` | ключ шлюза (секрет) | — |
| `LLM_CA_BUNDLE` | путь к PEM корпоративного CA | пусто |
| `LLM_VERIFY_TLS` | проверять сертификат шлюза | `true` |
| `LLM_RESPONSE_FORMAT` | способ запроса JSON у шлюза | `prompt` |
| `LLM_MAX_CONCURRENCY`, `LLM_TIMEOUT`, `LLM_TOTAL_TIMEOUT`, `LLM_RETRY_*`, `LLM_EMPTY_*` | пределы вызовов модели | см. `config.yaml` |
| `WORKER_MAX_JOBS`, `WORKER_JOB_TIMEOUT`, `WORKER_MAX_ATTEMPTS` | пределы воркера | `2`, `600`, `3` |
| `JOURNAL_RETENTION_MONTHS`, `SOFFICE_CACHE_DAYS` | сроки хранения журнала и кэша конвертации | `3`, `7` |
| `APP_VERSION` | версия кода, задана в образе при сборке | хэш коммита |

`AUTH_DEV_MODE` — прежнее имя `AUTH_DISABLED`, работает как синоним.

## Сертификат шлюза

Если шлюз подписан корпоративным CA, создайте ConfigMap и укажите путь в `LLM_CA_BUNDLE`:

```bash
kubectl -n cargo-assistant create configmap cargo-ca --from-file=ca.pem=./ca.pem
```

В `config.yaml`: `LLM_CA_BUNDLE: /etc/cargo-ca/ca.pem`. ConfigMap смонтирован в api и worker в
`/etc/cargo-ca` (необязательный: без него поды стартуют). Отключать проверку сертификата
(`LLM_VERIFY_TLS=false`) можно только для отладки.

## Обновление и откат

Новая версия: собрать образ, заменить тег в `api.yaml`, `worker.yaml`, `migrate.yaml`, повторить
шаги 5–6. Откат: вернуть прежний тег и повторить шаг 6; миграции назад не откатываются
автоматически (`alembic downgrade` — только по решению разработчиков).

## Известные ограничения первой версии

- Вход отключён: все работают под одним пользователем (`AUTH_DEV_USER_ID`, по умолчанию
  `dev-user`, имя «Локальный пользователь»), видят все полисы, сессии и архив; роли и группы не
  различаются. Ingress должен быть закрыт сетью контура. Привязка результатов к пользователю
  (claim `sub` Keycloak, имя из `preferred_username`; каждый видит только свои сессии) будет
  сделана в T-36, вход через Keycloak (authorization code flow с cookie сессии) — отдельной
  задачей после ответа на П-14.
- `FORWARDED_ALLOW_IPS: "*"` допустим только за доверенным ingress; в `config.yaml` лучше
  указать его адрес или подсеть.
- Образ содержит LibreOffice (около 900 МБ) для чтения `.doc`; без него `.doc` отклоняются.
- Хранилище файлов — общий PVC `ReadWriteMany`; на `ReadWriteOnce` поды api и worker на разных
  узлах не увидят файлы друг друга.
- Мониторинг (Superset) читает представления схемы `monitoring` из Postgres; их создаёт
  миграция, настройка Superset вне этой инструкции.
- Миграции применяются заданием, а не при старте пода: после обновления образа задание нужно
  запустить заново.
- Образ не подписан, секрет доступа к реестру (`imagePullSecrets`) в манифестах не описан:
  добавьте его, если реестр требует вход.

## Вход через Keycloak

При `AUTH_DISABLED=false` страницы требуют вход: `/auth/login` отправляет в Keycloak
(authorization code flow, PKCE S256), `/auth/callback` проверяет `state`, меняет код на токен,
проверяет подпись токена и кладёт в cookie `cargo_session` подписанную `SESSION_SECRET` запись
(`sub`, `preferred_username`, роли, группы; токен Keycloak в cookie не хранится). `/auth/logout`
стирает cookie и завершает сессию в Keycloak. Истёкшая или поддельная сессия — перенаправление
на вход; запросы `/api/*` без токена получают 401, с заголовком `Authorization: Bearer` проверяются
как раньше. Токен без `sub` отклоняется. В клиенте Keycloak включите стандартный поток, PKCE S256
и redirect URI `<адрес>/auth/callback`; `aud` токена должен содержать `KEYCLOAK_CLIENT_ID`.
Создать ключ: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
