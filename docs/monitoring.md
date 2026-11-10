# Мониторинг: журнал и представления

Документ для того, кто строит дашборд и письма в Superset. Устройство и решение — в разделе
«Мониторинг (D-34)» [architecture.md](architecture.md). Приложение пишет журнал, Superset читает
только представления схемы `monitoring` (`monitoring.v_*`); сами таблицы журнала читать не нужно.
Представления создаёт миграция `0004` и только в Postgres; в SQLite их нет. Ролей и прав на чтение
мы не создаём — их выдаёт пользователь.

## Термины

- **Сессия** — запуск проверки одной декларации: задача `reconcile` (строка `jobs`).
- **Попытка** — один захват задачи воркером (строка `job_runs`). У сессии может быть несколько
  попыток: возврат в очередь, ожидание профиля полиса, повтор после ошибки.
- **Исход сессии** — `success` (проверка выполнена), `error` (ошибка или превышено число
  попыток), пусто — сессия ещё не завершена. Это не статус сверки («совпадает», «не совпадает»,
  «требует проверки»): статусы по полям — в представлениях качества (T-23).
- **Исход попытки** — `running`, `success`, `error`, `timeout`, `requeued` (задачу вернули в
  очередь, потому что воркер замолчал), `waiting` (ждёт профиль полиса).
- **Чанк** — один вызов модели при проверке декларации (строка `llm_calls`).
- **Гонка при загрузке** — задача по тому же файлу (одинаковый `sha256`) создана, пока
  предыдущая задача по нему не завершена.
- **Живой воркер** — воркер без отметки остановки, подавший сигнал не позднее 180 секунд назад.

Время везде в UTC без часового пояса. Периоды `day` и `week` — даты по UTC (неделя с понедельника).

## Что не попадает в журнал и представления

Значения полей, имена файлов и тексты документов. В представлениях только идентификаторы, коды,
счётчики и время. Текст ошибки хранится в `job_runs.error_text` (он может содержать имя файла), но
ни одно представление его не читает: наружу выходит только класс ошибки (`error_class`, например
`KeyError`). Это закреплено тестом `test_exposes_no_error_text_file_name_or_field_value_in_any_view`.

## Таблицы журнала

| Таблица | Строка | Колонки журнала |
|---|---|---|
| `worker_heartbeats` | процесс воркера | `id` (случайный ключ процесса), `host`, `pid`, `version`, `started_at`, `last_seen` (сигнал раз в 30 секунд), `running` (задач в работе), `stopped_at` (пусто, пока воркер не остановлен штатно) |
| `job_runs` | попытка | `id`, `job_id`, `attempt`, `worker_id`, `queued_at` (когда задача встала в очередь), `started_at` (захват), `finished_at`, `outcome`, `error_class`, `error_text` (не выводится), `timings` (секунды по стадиям, JSON), `code_version`, `cards_version`, `profile_version`, `prompts_version`, `model` |
| `jobs` (дополнена) | задача | `queued_at`, `uploaded_by`, `access_group`, `file_sha256`, `outcome` (исход сессии), `finished_at` |
| `llm_calls` (дополнена) | вызов модели | `outcome` (`success`, `invalid_json`; значения `retry` и `timeout` появятся, когда клиент модели начнёт их сообщать), `subject`, `questions`, `dropped`, `created_at` |
| `declarations` (дополнена) | декларация | `places_expected`, `places_answered` (заполняются в T-23) |
| `check_results` (дополнена) | результат | `created_at` |

Хранение: 3 месяца (`JOURNAL_RETENTION_MONTHS`). Раз в сутки (`WORKER_PURGE_INTERVAL`, при старте
воркера и далее каждые 86400 секунд) удаляются строки `job_runs`, `llm_calls` и `worker_heartbeats`
старше срока. Задачи, декларации и результаты сверки не удаляются.

## Представления

| Представление | Строка | Колонки |
|---|---|---|
| `v_runs` | попытка | `run_id`, `job_id`, `kind`, `attempt`, `worker_id`, `queued_at`, `started_at`, `finished_at`, `outcome`, `error_class`, `seconds` (длительность), `wait_seconds` (ожидание в очереди до захвата), `timings` (JSON), `code_version`, `cards_version`, `profile_version`, `prompts_version`, `model` |
| `v_session_outcomes` | сессия (`reconcile`) | `job_id`, `declaration_id`, `uploaded_by`, `access_group`, `status` (состояние задачи), `outcome`, `attempts`, `created_at`, `finished_at`, `seconds`, `error_class` и версии последней попытки |
| `v_worker_status` | воркер | `worker_id`, `host`, `pid`, `version`, `started_at`, `last_seen`, `running`, `stopped_at`, `silent_seconds` (с последнего сигнала), `alive` (1 — живой) |
| `v_queue_status` | вид задачи | `kind`, `queued` (в очереди), `running` (в работе), `waiting` (ждут профиль), `oldest_queued_seconds` (сколько ждёт самая старая) |
| `v_queue_wait_daily` | день и вид | `day`, `kind`, `runs`, `avg_seconds`, `p50_seconds`, `p95_seconds` — ожидание от постановки до захвата |
| `v_stuck_sessions` | задача | `job_id`, `kind`, `declaration_id`, `run_id`, `worker_id`, `started_at`, `last_seen`, `silent_seconds` — задачи в работе на воркере, который молчит больше 180 секунд |
| `v_outcomes_daily` | день | `day`, `sessions`, `success`, `failed`, `success_share`, `failed_share` — завершённые сессии |
| `v_upload_races` | задача-гонка | `job_id`, `earlier_job_id`, `created_at` — вспомогательное представление для гонок |
| `v_errors_daily` | день, категория, класс | `day`, `category` (`error` — неудачные попытки, включая `timeout`; `race` — гонки), `error_class` (для гонок пусто), `runs` |
| `v_failure_streak` | одна строка | `streak` — сколько последних завершённых попыток подряд неуспешны (`error`, `timeout`, `requeued`); `waiting` пропускается, `success` обрывает ряд |
| `v_duration_daily` | день, вид, стадия | `day`, `kind`, `stage` (`total` — вся попытка, иначе имя стадии), `runs`, `avg_seconds`, `p50_seconds`, `p95_seconds`, `max_seconds` — только успешные попытки |
| `v_versions` | день, вид и набор версий | `day`, `kind`, `code_version`, `cards_version`, `profile_version`, `prompts_version`, `model`, `runs`, `success`, `failed`, `avg_seconds`, `p95_seconds` |
| `v_usage_daily` | день | `day`, `users`, `uploads`, `declarations`, `shipments` |
| `v_usage_weekly` | неделя | `week`, `users`, `uploads`, `declarations`, `shipments` |
| `v_alerts` | алерт | `alert`, `firing` (0/1), `value`, `threshold`, `note` |

`users` — число разных загрузивших, `uploads` — число запусков проверки, `declarations` и
`shipments` — декларации и перевозки по дате создания декларации.

## Алерты

`v_alerts` даёт по строке на алерт. Пороги заданы константами в самом представлении
(`migrations/monitoring.py`); стартовые значения пересматриваются через две недели (T-24).
В Superset каждый алерт — запрос ниже; условие срабатывания — «результат больше 0». Колонки
`value`, `threshold` и `note` пригодны для текста письма.

| Алерт | Срабатывает, когда | `value` | `threshold` |
|---|---|---|---|
| `worker_down` | нет сигнала живого воркера больше 180 секунд (в том числе когда воркеров нет или все остановлены) | секунд с последнего сигнала, 86400 если живых воркеров нет | 180 |
| `queue_stalled` | самая старая задача ждёт в очереди больше 900 секунд | секунд ожидания | 900 |
| `stuck_sessions` | есть задача в работе на воркере, молчащем больше 180 секунд | число таких задач | 0 |
| `consecutive_failures` | 3 и более неуспешных попытки подряд | длина ряда | 3 |
| `failure_share_1h` | за последний час завершено не меньше 5 сессий и неуспешных больше пятой части | доля неуспешных | 0.2 |
| `upload_race_1h` | за последний час создана хотя бы одна задача по файлу, который уже обрабатывается | число задач-гонок | 0 |

Запросы Superset (срабатывание — значение больше 0):

```sql
-- worker_down
SELECT firing FROM monitoring.v_alerts WHERE alert = 'worker_down'

-- queue_stalled
SELECT firing FROM monitoring.v_alerts WHERE alert = 'queue_stalled'

-- stuck_sessions
SELECT firing FROM monitoring.v_alerts WHERE alert = 'stuck_sessions'

-- consecutive_failures
SELECT firing FROM monitoring.v_alerts WHERE alert = 'consecutive_failures'

-- failure_share_1h
SELECT firing FROM monitoring.v_alerts WHERE alert = 'failure_share_1h'

-- upload_race_1h
SELECT firing FROM monitoring.v_alerts WHERE alert = 'upload_race_1h'
```

Один запрос на все алерты, для письма со списком сработавших:

```sql
SELECT alert, value, threshold, note FROM monitoring.v_alerts WHERE firing = 1
```

Что смотреть, когда алерт сработал:

| Алерт | Запрос |
|---|---|
| `worker_down` | `SELECT * FROM monitoring.v_worker_status ORDER BY last_seen DESC` |
| `queue_stalled` | `SELECT * FROM monitoring.v_queue_status` |
| `stuck_sessions` | `SELECT * FROM monitoring.v_stuck_sessions` |
| `consecutive_failures` | `SELECT run_id, job_id, outcome, error_class, finished_at FROM monitoring.v_runs WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 10` |
| `failure_share_1h` | `SELECT * FROM monitoring.v_session_outcomes WHERE outcome = 'error' AND finished_at >= timezone('utc', now()) - interval '1 hour'` |
| `upload_race_1h` | `SELECT * FROM monitoring.v_upload_races WHERE created_at >= timezone('utc', now()) - interval '1 hour'` |

## Тесты

Тесты представлений и алертов — `tests/migrations/test_monitoring.py`, маркер `postgres`. Каждый
тест создаёт отдельную пустую базу на сервере из `TEST_DATABASE_URL`, применяет миграции,
наполняет таблицы данными со смещениями от текущего времени сервера и удаляет базу; тесты не
мешают друг другу и ничего не оставляют. Без `TEST_DATABASE_URL` тесты пропускаются, причина
видна в выводе `pytest`. Запуск — в [CLAUDE.md](../CLAUDE.md).
