import argparse
import os

import uvicorn

from app.database import engine


def main():
    parser = argparse.ArgumentParser(description="Запуск ilya_safronov")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    print(f"Проект: ilya_safronov; база: {engine.url.database}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("APP_PORT", "8000")), reload=args.reload)


if __name__ == "__main__":
    main()
