from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Appointment, Service, Slot, Specialist
from scripts.seed import build_rows, seed


def test_small_seed_is_reproducible_and_booking_ids_continue(client, auth):
    seed("small")
    with SessionLocal() as db:
        counts = [db.scalar(select(func.count()).select_from(model)) for model in (Specialist, Service, Slot, Appointment)]
        first = db.execute(select(Appointment.id, Appointment.slot_id, Appointment.status).order_by(Appointment.id)).all()
    assert counts == [10, 10, 500, 300]
    seed("small")
    with SessionLocal() as db:
        second = db.execute(select(Appointment.id, Appointment.slot_id, Appointment.status).order_by(Appointment.id)).all()
    assert first == second
    slots = client.get("/api/slots?service_id=1&date=2026-10-12", auth=auth).json()
    response = client.post("/api/appointments", auth=auth, json={"slot_id": slots[0]["id"], "service_id": 1, "client_name": "Анна"})
    assert response.status_code == 201
    assert response.json()["id"] > 300


def test_large_seed_populates_all_specialists_without_slot_collisions():
    specialists, services, slots, appointments = build_rows("large")
    assert [len(rows) for rows in (specialists, services, slots, appointments)] == [200, 30, 200_000, 50_000]
    slots_by_id = {row["id"]: row for row in slots}
    assert len({row["slot_id"] for row in appointments}) == 50_000
    assert {slots_by_id[row["slot_id"]]["specialist_id"] for row in appointments} == set(range(1, 201))
    assert sum(row["status"] == "cancelled" for row in appointments) == 5000
