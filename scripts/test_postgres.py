import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    url = make_url(os.environ["DATABASE_URL"])
    test_database = (url.database or "ilya_safronov").removesuffix("_test") + "_test"
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = url.set(database=test_database).render_as_string(hide_password=False)
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"Проект: ilya_safronov; тестовая БД: {test_database}", flush=True)
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
