# ilya_safronov

Репозиторий: https://github.com/dumerpostpunk/ilya_safronov_hw1

ДЗ № 1, вариант 3. Запись на приём: специалисты, услуги, свободные слоты, создание и отмена записей, фильтры и сводка.

Python 3.14, PostgreSQL 18. База и схема: `ilya_safronov`.
В `.env` указывается `DATABASE_URL=postgresql+psycopg://postgres:пароль@localhost:5432/ilya_safronov` и `APP_PORT=8010`.

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

.\.venv\Scripts\python.exe -m scripts.run
.\.venv\Scripts\python.exe -m scripts.test_postgres
