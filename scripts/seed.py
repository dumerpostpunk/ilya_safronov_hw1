import argparse
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text

from app.database import DB_SCHEMA, engine, init_db
from app.models import Appointment, Service, Slot, Specialist

ANCHOR = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)

NAMES = [
    ("Анна Смирнова", "Терапевт"), ("Иван Кузнецов", "Кардиолог"),
    ("Мария Попова", "Невролог"), ("Алексей Васильев", "Офтальмолог"),
    ("Елена Петрова", "Дерматолог"), ("Дмитрий Соколов", "Эндокринолог"),
    ("Ольга Михайлова", "Терапевт"), ("Сергей Новиков", "Кардиолог"),
    ("Наталья Фёдорова", "Невролог"), ("Павел Морозов", "Ортопед"),
]
SERVICE_NAMES = [
    ("Первичная консультация", 60), ("Повторная консультация", 30),
    ("Профилактический осмотр", 45), ("Кардиологическая консультация", 60),
    ("Неврологическая консультация", 45), ("Проверка зрения", 30),
    ("Дерматологическая консультация", 30), ("Эндокринологическая консультация", 45),
    ("Консультация ортопеда", 60), ("Краткий осмотр", 30),
    ("Расширенная консультация", 60), ("Контрольный осмотр", 30),
    ("Диагностическая консультация", 45), ("Оценка результатов", 30),
    ("Плановый приём", 60), ("Дополнительный осмотр", 45),
    ("Консультация по результатам", 30), ("Первичный осмотр", 60),
    ("Консультация специалиста", 45), ("Краткая консультация", 30),
    ("План лечения", 45), ("Контроль лечения", 30),
    ("Повторная диагностика", 60), ("Оценка симптомов", 30),
    ("Профильный осмотр", 45), ("Профилактическая консультация", 30),
    ("Осмотр перед процедурой", 45), ("Заключительная консультация", 60),
    ("Оценка состояния", 30), ("Комплексный приём", 60),
]


def chunks(rows, size=5000):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def build_rows(size: str):
    if size == "small":
        specialist_count, service_count, slot_count, appointment_count = 10, 10, 500, 300
    elif size == "large":
        specialist_count, service_count, slot_count, appointment_count = 200, 30, 200_000, 50_000
    else:
        raise ValueError("size должен быть small или large")

    specialist_rows = [
        {"id": i + 1, "full_name": NAMES[i % len(NAMES)][0] + (f" {i + 1}" if i >= len(NAMES) else ""),
         "specialization": NAMES[i % len(NAMES)][1]}
        for i in range(specialist_count)
    ]
    service_rows = [
        {"id": i + 1, "name": SERVICE_NAMES[i][0], "duration_minutes": SERVICE_NAMES[i][1]}
        for i in range(service_count)
    ]

    slot_rows = []
    for i in range(slot_count):
        specialist_id = i % specialist_count + 1
        specialist_day_index = i // specialist_count
        day_offset = specialist_day_index // 10
        hour_offset = specialist_day_index % 10
        starts_at = ANCHOR + timedelta(days=day_offset, hours=hour_offset)
        ends_at = starts_at + timedelta(hours=1)
        slot_rows.append({"id": i + 1, "specialist_id": specialist_id, "starts_at": starts_at, "ends_at": ends_at})


    slot_indices = random.Random(20261012).sample(range(slot_count), appointment_count)
    appointment_rows = []
    for i in range(appointment_count):
        slot = slot_rows[slot_indices[i]]
        service = service_rows[i % service_count]
        ends_at = slot["starts_at"] + timedelta(minutes=service["duration_minutes"])
        appointment_rows.append({
            "id": i + 1,
            "slot_id": slot["id"],
            "service_id": service["id"],
            "client_name": f"Тестовый клиент {i + 1:06d}",
            "starts_at": slot["starts_at"],
            "ends_at": ends_at,
            "status": "cancelled" if i % 10 == 0 else "booked",
            "created_at": slot["starts_at"] - timedelta(days=1),
        })
    return specialist_rows, service_rows, slot_rows, appointment_rows


def seed(size: str):
    specialist_rows, service_rows, slot_rows, appointment_rows = build_rows(size)
    init_db()

    with engine.begin() as conn:
        schema = (DB_SCHEMA or "public").replace('"', '""')
        if engine.dialect.name == "postgresql":
            conn.execute(text(
                f'TRUNCATE TABLE "{schema}"."appointments", "{schema}"."slots", '
                f'"{schema}"."services", "{schema}"."specialists" RESTART IDENTITY'
            ))
        else:
            for model in (Appointment, Slot, Service, Specialist):
                conn.execute(delete(model))
        for model, rows in (
            (Specialist, specialist_rows), (Service, service_rows),
            (Slot, slot_rows), (Appointment, appointment_rows),
        ):
            for group in chunks(rows):
                conn.execute(model.__table__.insert(), group)


        if engine.dialect.name == "postgresql":
            for table_name in ("specialists", "services", "slots", "appointments"):
                qualified_table = f'"{schema}"."{table_name}"'
                conn.execute(
                    text(
                        f"""
                        SELECT setval(
                            pg_get_serial_sequence(:qualified_name, 'id'),
                            COALESCE((SELECT MAX(id) FROM {qualified_table}), 1),
                            EXISTS (SELECT 1 FROM {qualified_table})
                        )
                        """
                    ),
                    {"qualified_name": qualified_table},
                )

    print(f"Наполнение завершено: режим={size}")
    print(f"База: {engine.url.database}; схема: {DB_SCHEMA or 'default'}; проект: ilya_safronov")
    print(f"Специалисты: {len(specialist_rows)}")
    print(f"Услуги: {len(service_rows)}")
    print(f"Слоты: {len(slot_rows)}")
    print(f"Записи: {len(appointment_rows)}")


def main():
    parser = argparse.ArgumentParser(description="Воспроизводимое наполнение базы ilya_safronov")
    parser.add_argument("--size", choices=["small", "large"], required=True, help="small — разработка, large — рабочий объём")
    args = parser.parse_args()
    seed(args.size)


if __name__ == "__main__":
    main()
