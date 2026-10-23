from datetime import datetime, timedelta, timezone

import pytest

from app.database import engine


def test_appointments_require_authorization(client):
    response = client.get("/api/appointments")
    assert response.status_code == 401


def test_appointment_list_returns_pagination_contract(client, auth):
    response = client.get("/api/appointments?page=1&size=20", auth=auth)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert response.json()["page"] == 1


def test_booking_fails_when_service_is_longer_than_slot(client, auth):
    response = client.post("/api/appointments", auth=auth, json={"slot_id": 3, "service_id": 2, "client_name": "Анна"})
    assert response.status_code == 422


def test_overlapping_booking_is_rejected(client, auth):
    first = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 2, "client_name": "Иван"})
    assert first.status_code == 201
    second = client.post("/api/appointments", auth=auth, json={"slot_id": 2, "service_id": 1, "client_name": "Мария"})
    assert second.status_code == 409


def test_cancel_makes_slot_available_again(client, auth):
    created = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"})
    assert created.status_code == 201
    appointment_id = created.json()["id"]
    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel", auth=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["appointment"]["status"] == "cancelled"
    second = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Мария"})
    assert second.status_code == 201


def test_summary_returns_specialist_metrics(client, auth):
    response = client.get("/api/summary?start_date=2026-10-12&end_date=2026-10-13", auth=auth)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["specialist"] == "Иван Иванов"
    assert "load_percent" in data["items"][0]


def test_missing_appointment_returns_404(client, auth):
    response = client.get("/api/appointments/999", auth=auth)
    assert response.status_code == 404


def test_available_slots_endpoint_returns_slots(client, auth):
    response = client.get("/api/slots?service_id=1&date=2026-10-12", auth=auth)
    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert "starts_at" in response.json()[0]


def test_slot_with_exact_service_duration_is_available(client, auth):
    response = client.get("/api/slots?service_id=1&date=2026-10-12", auth=auth)
    assert response.status_code == 200
    assert 3 in {row["id"] for row in response.json()}


def test_search_checks_service_interval_instead_of_entire_slot(client, auth):
    booked = client.post("/api/appointments", auth=auth, json={"slot_id": 2, "service_id": 1, "client_name": "Иван"})
    assert booked.status_code == 201

    response = client.get("/api/slots?service_id=1&date=2026-10-12", auth=auth)
    assert 1 in {row["id"] for row in response.json()}
    long_service = client.get("/api/slots?service_id=2&date=2026-10-12", auth=auth)
    assert 1 not in {row["id"] for row in long_service.json()}
    created = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Анна"})
    assert created.status_code == 201


def test_search_excludes_overlapping_bookings(client, auth):
    created = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 2, "client_name": "Анна"})
    assert created.status_code == 201
    response = client.get("/api/slots?service_id=1&date=2026-10-12", auth=auth)
    assert {row["id"] for row in response.json()} == {3}


@pytest.mark.parametrize("name", ["  ", " А ", "", "А" * 121])
def test_invalid_client_name_is_rejected(client, auth, name):
    response = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": name})
    assert response.status_code == 422


def test_name_is_trimmed_and_datetimes_include_timezone(client, auth):
    response = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "  Анна  "})
    assert response.status_code == 201
    assert response.json()["client_name"] == "Анна"
    assert datetime.fromisoformat(response.json()["starts_at"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize("path", [
    "/api/specialists", "/api/services", "/api/slots?service_id=1",
    "/api/appointments/1", "/api/summary",
])
def test_read_operations_require_authentication(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/appointments", "/api/appointments/1/cancel"])
def test_write_operations_require_authentication(client, path):
    assert client.post(path, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"}).status_code == 401


def test_wrong_password_is_rejected(client):
    response = client.get("/api/services", auth=("demo", "wrong"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


@pytest.mark.parametrize("query", ["page=0", "size=101", "status=unknown", "specialist_id=0"])
def test_invalid_list_parameters_are_rejected(client, auth, query):
    assert client.get("/api/appointments?" + query, auth=auth).status_code == 422


def test_pagination_and_filters_use_all_matching_records(client, auth):
    first = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"}).json()
    second = client.post("/api/appointments", auth=auth, json={"slot_id": 3, "service_id": 1, "client_name": "Анна"}).json()
    response = client.get("/api/appointments?page=2&size=1", auth=auth).json()
    assert response["total"] == 2
    assert [row["id"] for row in response["items"]] == [second["id"]]
    client.post(f"/api/appointments/{first['id']}/cancel", auth=auth)
    response = client.get("/api/appointments?status=cancelled&specialist_id=1", auth=auth).json()
    assert response["total"] == 1
    assert response["items"][0]["id"] == first["id"]


def test_card_contains_related_entities(client, auth):
    created = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"}).json()
    card = client.get(f"/api/appointments/{created['id']}", auth=auth).json()
    assert card == created
    assert card["specialist"] == "Иван Иванов"
    assert card["service"] == "Короткая консультация"


def test_second_cancellation_returns_conflict(client, auth):
    created = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"}).json()
    path = f"/api/appointments/{created['id']}/cancel"
    assert client.post(path, auth=auth).status_code == 200
    assert client.post(path, auth=auth).status_code == 409


@pytest.mark.parametrize("payload", [
    {"slot_id": 999, "service_id": 1, "client_name": "Иван"},
    {"slot_id": 1, "service_id": 999, "client_name": "Иван"},
])
def test_booking_missing_entities_returns_404(client, auth, payload):
    assert client.post("/api/appointments", auth=auth, json=payload).status_code == 404


def test_missing_service_and_missing_cancellation_return_404(client, auth):
    assert client.get("/api/slots?service_id=999", auth=auth).status_code == 404
    assert client.post("/api/appointments/999/cancel", auth=auth).status_code == 404


def test_summary_counts_bookings_cancellations_and_load(client, auth):
    first = client.post("/api/appointments", auth=auth, json={"slot_id": 1, "service_id": 1, "client_name": "Иван"}).json()
    client.post("/api/appointments", auth=auth, json={"slot_id": 3, "service_id": 1, "client_name": "Анна"})
    client.post(f"/api/appointments/{first['id']}/cancel", auth=auth)
    response = client.get("/api/summary?start_date=2026-10-12&end_date=2026-10-13", auth=auth)
    row = response.json()["items"][0]
    assert row["total_appointments"] == 2
    assert row["booked_appointments"] == 1
    assert row["cancelled_appointments"] == 1
    assert row["cancelled_percent"] == 50
    assert row["booked_minutes"] == 30
    assert row["available_minutes"] == 150
    assert row["load_percent"] == 20
    empty_period = client.get("/api/summary?start_date=2026-10-13&end_date=2026-10-14", auth=auth)
    assert empty_period.json()["items"][0]["total_appointments"] == 0


def test_invalid_summary_period_returns_422(client, auth):
    response = client.get("/api/summary?start_date=2026-10-13&end_date=2026-10-12", auth=auth)
    assert response.status_code == 422


def test_sql_measurements_and_cache_policy_are_present(client, auth):
    response = client.get("/api/services", auth=auth)
    assert int(response.headers["X-SQL-Count"]) == 1
    assert float(response.headers["X-SQL-Time-Ms"]) >= 0
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Конкурентное бронирование требует PostgreSQL")
def test_concurrent_bookings_cannot_overlap(client, auth):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def book(slot_id):
        barrier.wait(timeout=10)
        return client.post("/api/appointments", auth=auth, json={"slot_id": slot_id, "service_id": 2, "client_name": "Иван"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(book, [1, 2])) == [201, 409]
