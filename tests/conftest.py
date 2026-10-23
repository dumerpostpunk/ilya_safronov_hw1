import os
from uuid import uuid4


test_database_url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
if test_database_url.startswith("postgresql"):
    from sqlalchemy.engine import make_url

    if not (make_url(test_database_url).database or "").endswith("_test"):
        raise ValueError("TEST_DATABASE_URL должен указывать на отдельную БД с суффиксом _test")
    os.environ["DB_SCHEMA"] = "test_" + uuid4().hex
os.environ["DATABASE_URL"] = test_database_url
os.environ["APP_USERNAME"] = "demo"
os.environ["APP_PASSWORD"] = "demo123"

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.database import Base, DB_SCHEMA, SessionLocal, engine, init_db
from app.main import app
from app.models import Service, Slot, Specialist


@pytest.fixture
def test_database():
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    if engine.dialect.name == "postgresql":
        from sqlalchemy.schema import DropSchema

        with engine.begin() as connection:
            connection.execute(DropSchema(DB_SCHEMA))


@pytest.fixture
def client(test_database):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    now = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        specialist = Specialist(full_name="Иван Иванов", specialization="Терапевт")
        db.add(specialist)
        db.flush()
        service30 = Service(name="Короткая консультация", duration_minutes=30)
        service60 = Service(name="Длинная консультация", duration_minutes=60)
        db.add_all([service30, service60])
        db.flush()
        db.add_all([
            Slot(specialist_id=specialist.id, starts_at=now, ends_at=now + timedelta(minutes=60)),
            Slot(specialist_id=specialist.id, starts_at=now + timedelta(minutes=30), ends_at=now + timedelta(minutes=90)),
            Slot(specialist_id=specialist.id, starts_at=now + timedelta(hours=2), ends_at=now + timedelta(hours=2, minutes=30)),
        ])
        db.commit()
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def auth():
    return ("demo", "demo123")
