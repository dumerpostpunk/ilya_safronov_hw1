# ilya_safronov

Репозиторий: https://github.com/dumerpostpunk/ilya_safronov_hw1

ДЗ № 1, вариант 3. Запись на приём: специалисты, услуги, свободные слоты, создание и отмена записей, фильтры и сводка.

Нужны Python 3.14 и PostgreSQL 18 с запущенной службой. База и схема: `ilya_safronov`.
Создание базы в PowerShell (пароль пользователя `postgres` вводится по запросу):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d postgres -c "CREATE DATABASE ilya_safronov;"
```

Создать в корне `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:ПАРОЛЬ@localhost:5432/ilya_safronov
DB_SCHEMA=ilya_safronov
APP_USERNAME=demo
APP_PASSWORD=demo123
APP_PORT=8010
```

В пароле для URL символы `@`, `:`, `/`, `%` кодируются как `%40`, `%3A`, `%2F`, `%25`. Схема и таблицы создаются автоматически при наполнении или запуске.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.seed --size small
python -m scripts.run
```

Интерфейс: http://127.0.0.1:8010. Вход: `demo` / `demo123`.
API и форматы запросов: http://127.0.0.1:8010/docs.
Для большого набора: `python -m scripts.seed --size large`. Наполнение очищает предыдущие данные.

```powershell
python -m pytest -q -p no:cacheprovider
python -m bench.measure --base-url http://127.0.0.1:8010
```

Результаты замеров — `bench/results_small.csv` и `bench/results_large.csv`.
Скриншоты — `screenshots/`, отчёт — [REPORT_DZ1.docx](report/REPORT_DZ1.docx).

Обычный pytest использует SQLite в памяти: 39 passed, 1 skipped. Для полного прогона на PostgreSQL сначала создать отдельную БД, затем запустить тесты:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d postgres -c "CREATE DATABASE ilya_safronov_test;"
python -m scripts.test_postgres
```

Замеры: после каждого наполнения запустить сервер без `--reload`, в другом терминале выполнить `python -m bench.measure --base-url http://127.0.0.1:8010 --output bench/results_small.csv` (для большого набора — `results_large.csv`). По умолчанию 5 прогревов и 30 учитываемых повторов. Серия добавляет 35 отменённых записей.

## API

Все операции ниже требуют HTTP Basic (`demo` / `demo123`, либо значения из `.env`). Данные — JSON, даты — `YYYY-MM-DD`, время в ответах — ISO 8601 с UTC. Период `[start_date, end_date)`, фильтр дня также UTC.

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| GET `/api/specialists` | — | 200, массив `{id, full_name, specialization}` | 401 |
| GET `/api/services` | — | 200, массив `{id, name, duration_minutes}` | 401 |
| GET `/api/slots` | `service_id>0` обязателен; `date`, `specialist_id>0` необязательны; `limit=100`, 1–500 | 200, массив `{id, specialist_id, specialist, starts_at, ends_at}` | 401, 404, 422 |
| GET `/api/appointments` | `page=1` ≥1; `size=20`, 1–100; `status` (`booked`/`cancelled`), `specialist_id>0` необязательны | 200, `{items: [Appointment], total, page, size}` | 401, 422 |
| GET `/api/appointments/{id}` | Целочисленный ID | 200, `Appointment` | 401, 404, 422 |
| POST `/api/appointments` | JSON: `slot_id>0`, `service_id>0`, `client_name` — 2–120 символов после удаления пробелов по краям | 201, `Appointment` | 401, 404, 409, 422 |
| POST `/api/appointments/{id}/cancel` | Целочисленный ID | 200, `{message, appointment: Appointment}` | 401, 404, 409, 422 |
| GET `/api/summary` | `start_date=2026-10-12`, `end_date=2026-11-12`; конец позже начала | 200, `{start_date, end_date, items: [Summary]}` | 401, 422 |

`Appointment`: `id`, `client_name`, `slot_id`, `service_id`, `service`, `duration_minutes`, `specialist_id`, `specialist`, `specialization`, `starts_at`, `ends_at`, `status`, `created_at`.

`Summary`: `specialist_id`, `specialist`, `specialization`, `total_appointments`, `booked_appointments`, `cancelled_appointments`, `cancelled_percent`, `booked_minutes`, `available_minutes`, `load_percent`. `available_minutes` — все минуты расписания за период. Проценты при нулевом знаменателе равны 0.

Ошибки имеют вид `{"detail": "сообщение"}`; для валидации 422 `detail` — массив ошибок. 404 — сущность отсутствует, 409 — пересечение приёмов или повторная отмена, 422 — неверные параметры либо услуга длиннее слота. Пересечения проверяются у специалиста на интервале услуги; соприкасающиеся границы разрешены. Отмена сохраняет историю.

Ответы API содержат `X-SQL-Count` и `X-SQL-Time-Ms` (сумма клиентских длительностей `cursor.execute`), `Cache-Control: no-store`. Полная схема типов: `/openapi.json`.
