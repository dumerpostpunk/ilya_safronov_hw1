import argparse
import csv
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def percentile(values, p):
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return data[lo]
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def main():
    parser = argparse.ArgumentParser(description="Исходные замеры HTTP-ответов и SQL-запросов")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default=os.getenv("APP_USERNAME", "demo"))
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", "demo123"))
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--date", default="2026-10-12", help="дата, на которую искать свободный слот")
    parser.add_argument("--output", default="bench/results.csv")
    args = parser.parse_args()
    if args.repeats < 20:
        raise SystemExit("По методичке требуется не менее 20 повторов; используй --repeats 20 или больше.")
    if args.warmup < 1:
        parser.error("--warmup должен быть не меньше 1: прогрев обязателен")
    try:
        date.fromisoformat(args.date)
    except ValueError:
        parser.error("--date должен быть датой в формате YYYY-MM-DD")

    session = requests.Session()
    session.auth = (args.username, args.password)
    session.headers.update({"Accept": "application/json"})
    base = args.base_url.rstrip("/")

    def send(method, path, **kwargs):
        response = session.request(method, base + path, timeout=120, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:500]}")
        return response


    listing = send("GET", "/api/appointments?page=1&size=20").json()
    if not listing["items"]:
        raise SystemExit("Нет записей для замера. Сначала выполни scripts/seed.py --size small или --size large.")
    appointment_id = listing["items"][0]["id"]
    slots = send("GET", f"/api/slots?service_id=1&date={args.date}&limit=500").json()
    if not slots:
        raise SystemExit(f"На {args.date} нет свободных слотов. Проверь дату или повтори наполнение.")
    slot_id = slots[0]["id"]
    service_id = 1
    booking_id = {"value": None}

    operations = [
        ("GET /api/appointments?page=1&size=20", lambda: send("GET", "/api/appointments?page=1&size=20")),
        (f"GET /api/appointments/{appointment_id}", lambda: send("GET", f"/api/appointments/{appointment_id}")),
        ("GET /api/specialists", lambda: send("GET", "/api/specialists")),
        ("GET /api/services", lambda: send("GET", "/api/services")),
        (f"GET /api/slots?service_id={service_id}&date={args.date}", lambda: send("GET", f"/api/slots?service_id={service_id}&date={args.date}&limit=100")),
        (f"GET /api/summary?start_date={args.date}", lambda: send("GET", f"/api/summary?start_date={args.date}&end_date={(date.fromisoformat(args.date)+timedelta(days=30)).isoformat()}")),
        ("POST /api/appointments", lambda: create()),
        ("POST /api/appointments/{id}/cancel", lambda: cancel()),
    ]

    def create():
        response = send("POST", "/api/appointments", json={"slot_id": slot_id, "service_id": service_id, "client_name": "Замер производительности"})
        booking_id["value"] = response.json()["id"]
        return response

    def cancel():
        if not booking_id["value"]:
            create()
        response = send("POST", f"/api/appointments/{booking_id['value']}/cancel")
        booking_id["value"] = None
        return response


    for _ in range(args.warmup):
        for _, operation in operations:
            operation()

    samples = {name: [] for name, _ in operations}
    for _ in range(args.repeats):
        for name, operation in operations:
            started = time.perf_counter()
            response = operation()
            elapsed_ms = (time.perf_counter() - started) * 1000
            try:
                sql_count = int(response.headers["X-SQL-Count"])
                sql_time_ms = float(response.headers["X-SQL-Time-Ms"])
            except (KeyError, ValueError) as exc:
                raise RuntimeError("Нет корректных SQL-метрик: проверь версию сервера перед замерами") from exc
            samples[name].append({"elapsed_ms": elapsed_ms, "sql_count": sql_count, "sql_time_ms": sql_time_ms})

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["operation", "repeats", "avg_http_ms", "p50_ms", "p95_ms", "max_ms", "avg_sql_ms", "avg_non_sql_ms", "avg_sql_count"]
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for name, rows in samples.items():
            elapsed = [x["elapsed_ms"] for x in rows]
            writer.writerow({
                "operation": name,
                "repeats": len(rows),
                "avg_http_ms": round(sum(elapsed) / len(elapsed), 3),
                "p50_ms": round(percentile(elapsed, 0.50), 3),
                "p95_ms": round(percentile(elapsed, 0.95), 3),
                "max_ms": round(max(elapsed), 3),
                "avg_sql_ms": round(sum(x["sql_time_ms"] for x in rows) / len(rows), 3),
                "avg_non_sql_ms": round(sum(x["elapsed_ms"] - x["sql_time_ms"] for x in rows) / len(rows), 3),
                "avg_sql_count": round(sum(x["sql_count"] for x in rows) / len(rows), 2),
            })
    print(f"Замеры сохранены: {output.resolve()}")
    with output.open(encoding="utf-8-sig", newline="") as stream:
        print("\n" + stream.read())


if __name__ == "__main__":
    main()
