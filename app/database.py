import os
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:DB_PASSWORD@localhost:5432/ilya_safronov",
)
DB_SCHEMA = os.getenv("DB_SCHEMA", "ilya_safronov") if DATABASE_URL.startswith("postgresql") else None

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs["connect_args"] = {"connect_timeout": 5}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


request_sql_metrics: ContextVar[dict | None] = ContextVar("request_sql_metrics", default=None)


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._started_at_perf_counter = perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    metrics = request_sql_metrics.get()
    started = getattr(context, "_started_at_perf_counter", None)
    if metrics is not None and started is not None:
        metrics["count"] += 1
        metrics["time_ms"] += (perf_counter() - started) * 1000.0


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models
    from sqlalchemy import text

    if engine.dialect.name == "postgresql":
        safe_schema = DB_SCHEMA.replace('"', '""')
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{safe_schema}"'))
    Base.metadata.create_all(bind=engine)
