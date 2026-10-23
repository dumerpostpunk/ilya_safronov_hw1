import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.database import DB_SCHEMA, engine, get_db, init_db, request_sql_metrics
from app.models import Appointment, Service, Slot, Specialist

load_env_username = os.getenv("APP_USERNAME", "demo")
load_env_password = os.getenv("APP_PASSWORD", "demo123")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ilya_safronov — запись на приём", version="1.0.0", lifespan=lifespan)
security = HTTPBasic(auto_error=False)
STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    slot_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    client_name: str = Field(min_length=2, max_length=120)


def require_user(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация", headers={"WWW-Authenticate": "Basic"})
    username_ok = secrets.compare_digest(credentials.username.encode("utf-8"), load_env_username.encode("utf-8"))
    password_ok = secrets.compare_digest(credentials.password.encode("utf-8"), load_env_password.encode("utf-8"))
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.middleware("http")
async def collect_sql_metrics(request: Request, call_next):
    metrics = {"count": 0, "time_ms": 0.0}
    token = request_sql_metrics.set(metrics)
    try:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-SQL-Count"] = str(metrics["count"])
            response.headers["X-SQL-Time-Ms"] = f"{metrics['time_ms']:.3f}"
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        request_sql_metrics.reset(token)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_INDEX)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "database_schema": DB_SCHEMA or "default"}


def _specialist_name(db: Session, specialist_id: int) -> str:
    specialist = db.get(Specialist, specialist_id)
    return specialist.full_name if specialist else "Неизвестный специалист"


def _isoformat(value: datetime) -> str:

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _appointment_dict(db: Session, appointment: Appointment) -> dict:
    slot = db.get(Slot, appointment.slot_id)
    service = db.get(Service, appointment.service_id)
    specialist = db.get(Specialist, slot.specialist_id) if slot else None
    return {
        "id": appointment.id,
        "client_name": appointment.client_name,
        "slot_id": appointment.slot_id,
        "service_id": appointment.service_id,
        "service": service.name if service else "Неизвестная услуга",
        "duration_minutes": service.duration_minutes if service else None,
        "specialist_id": specialist.id if specialist else None,
        "specialist": specialist.full_name if specialist else "Неизвестный специалист",
        "specialization": specialist.specialization if specialist else "",
        "starts_at": _isoformat(appointment.starts_at),
        "ends_at": _isoformat(appointment.ends_at),
        "status": appointment.status,
        "created_at": _isoformat(appointment.created_at),
    }


@app.get("/api/specialists")
def list_specialists(db: Session = Depends(get_db), _user: str = Depends(require_user)):
    rows = db.scalars(select(Specialist).order_by(Specialist.id)).all()
    return [{"id": x.id, "full_name": x.full_name, "specialization": x.specialization} for x in rows]


@app.get("/api/services")
def list_services(db: Session = Depends(get_db), _user: str = Depends(require_user)):
    rows = db.scalars(select(Service).order_by(Service.id)).all()
    return [{"id": x.id, "name": x.name, "duration_minutes": x.duration_minutes} for x in rows]


@app.get("/api/slots")
def list_slots(
    service_id: int = Query(gt=0),
    date_filter: date | None = Query(default=None, alias="date"),
    specialist_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    if db.bind.dialect.name == "sqlite":
        candidate_end = func.datetime(Slot.starts_at, f"+{service.duration_minutes} minutes")
        slot_duration_minutes = func.round((func.julianday(Slot.ends_at) - func.julianday(Slot.starts_at)) * 1440, 6)
        overlap_start = func.julianday(Appointment.starts_at) < func.julianday(candidate_end)
        overlap_end = func.julianday(Appointment.ends_at) > func.julianday(Slot.starts_at)
    else:
        candidate_end = Slot.starts_at + timedelta(minutes=service.duration_minutes)
        slot_duration_minutes = func.extract("epoch", Slot.ends_at - Slot.starts_at) / 60
        overlap_start = Appointment.starts_at < candidate_end
        overlap_end = Appointment.ends_at > Slot.starts_at
    slot_alias = aliased(Slot)
    busy_overlap = (
        select(Appointment.id)
        .join(slot_alias, Appointment.slot_id == slot_alias.id)
        .where(
            slot_alias.specialist_id == Slot.specialist_id,
            Appointment.status == "booked",
            overlap_start,
            overlap_end,
        )
        .exists()
    )
    query = select(Slot).where(
        slot_duration_minutes >= service.duration_minutes,
        ~busy_overlap,
    )
    if date_filter:
        day_start = datetime.combine(date_filter, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        query = query.where(Slot.starts_at >= day_start, Slot.starts_at < day_end)
    if specialist_id:
        query = query.where(Slot.specialist_id == specialist_id)
    rows = db.scalars(query.order_by(Slot.starts_at, Slot.specialist_id).limit(limit)).all()
    return [
        {
            "id": x.id,
            "specialist_id": x.specialist_id,
            "specialist": _specialist_name(db, x.specialist_id),
            "starts_at": _isoformat(x.starts_at),
            "ends_at": _isoformat(x.ends_at),
        }
        for x in rows
    ]


@app.get("/api/appointments")
def list_appointments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(booked|cancelled)$"),
    specialist_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    query = select(Appointment)
    if status:
        query = query.where(Appointment.status == status)
    if specialist_id:
        query = query.join(Slot, Appointment.slot_id == Slot.id).where(Slot.specialist_id == specialist_id)
    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(Appointment.starts_at, Appointment.id).offset((page - 1) * size).limit(size)).all()
    return {"items": [_appointment_dict(db, x) for x in rows], "total": total, "page": page, "size": size}


@app.get("/api/appointments/{appointment_id}")
def get_appointment(appointment_id: int, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return _appointment_dict(db, appointment)


@app.post("/api/appointments", status_code=201)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    slot = db.get(Slot, payload.slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Слот не найден")


    db.execute(select(Specialist.id).where(Specialist.id == slot.specialist_id).with_for_update()).one()
    service = db.get(Service, payload.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    slot_minutes = int((slot.ends_at - slot.starts_at).total_seconds() // 60)
    if service.duration_minutes > slot_minutes:
        raise HTTPException(status_code=422, detail="Слот короче продолжительности услуги")
    starts_at = slot.starts_at
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    slot_alias = aliased(Slot)
    overlap = db.scalar(
        select(Appointment.id)
        .join(slot_alias, Appointment.slot_id == slot_alias.id)
        .where(
            slot_alias.specialist_id == slot.specialist_id,
            Appointment.status == "booked",
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        .limit(1)
    )
    if overlap is not None:
        raise HTTPException(status_code=409, detail="Время уже занято другой записью")
    appointment = Appointment(
        slot_id=slot.id,
        service_id=service.id,
        client_name=payload.client_name.strip(),
        starts_at=starts_at,
        ends_at=ends_at,
        status="booked",
        created_at=datetime.now(timezone.utc),
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return _appointment_dict(db, appointment)


@app.post("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db), _user: str = Depends(require_user)):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if appointment.status == "cancelled":
        raise HTTPException(status_code=409, detail="Запись уже отменена")
    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)
    return {"message": "Запись отменена; слот снова доступен", "appointment": _appointment_dict(db, appointment)}


@app.get("/api/summary")
def summary(
    start_date: date = Query(default=date(2026, 10, 12)),
    end_date: date = Query(default=date(2026, 11, 12)),
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
):
    if end_date <= start_date:
        raise HTTPException(status_code=422, detail="end_date должна быть позже start_date")
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.min, tzinfo=timezone.utc)

    if db.bind.dialect.name == "sqlite":
        slot_duration_minutes = (func.julianday(Slot.ends_at) - func.julianday(Slot.starts_at)) * 1440
        appointment_duration_minutes = (func.julianday(Appointment.ends_at) - func.julianday(Appointment.starts_at)) * 1440
    else:
        slot_duration_minutes = func.extract("epoch", Slot.ends_at - Slot.starts_at) / 60
        appointment_duration_minutes = func.extract("epoch", Appointment.ends_at - Appointment.starts_at) / 60

    slot_rows = db.execute(
        select(
            Slot.specialist_id,
            func.coalesce(func.sum(slot_duration_minutes), 0),
        )
        .where(Slot.starts_at >= start_dt, Slot.starts_at < end_dt)
        .group_by(Slot.specialist_id)
    ).all()
    total_minutes_by_specialist = {int(sid): float(minutes or 0) for sid, minutes in slot_rows}

    appt_rows = db.execute(
        select(
            Slot.specialist_id,
            func.count(Appointment.id),
            func.sum(case((Appointment.status == "booked", 1), else_=0)),
            func.sum(case((Appointment.status == "cancelled", 1), else_=0)),
            func.coalesce(func.sum(case((Appointment.status == "booked", appointment_duration_minutes), else_=0)), 0),
        )
        .join(Appointment, Appointment.slot_id == Slot.id)
        .where(Appointment.starts_at >= start_dt, Appointment.starts_at < end_dt)
        .group_by(Slot.specialist_id)
    ).all()
    stats = {
        int(sid): {
            "total_appointments": int(total or 0),
            "booked_appointments": int(booked or 0),
            "cancelled_appointments": int(cancelled or 0),
            "booked_minutes": float(minutes or 0),
        }
        for sid, total, booked, cancelled, minutes in appt_rows
    }

    specialists = db.scalars(select(Specialist).order_by(Specialist.id)).all()
    result = []
    for specialist in specialists:
        row = stats.get(specialist.id, {"total_appointments": 0, "booked_appointments": 0, "cancelled_appointments": 0, "booked_minutes": 0.0})
        slot_minutes = total_minutes_by_specialist.get(specialist.id, 0.0)
        total_appts = row["total_appointments"]
        result.append({
            "specialist_id": specialist.id,
            "specialist": specialist.full_name,
            "specialization": specialist.specialization,
            "total_appointments": total_appts,
            "booked_appointments": row["booked_appointments"],
            "cancelled_appointments": row["cancelled_appointments"],
            "cancelled_percent": round(row["cancelled_appointments"] * 100 / total_appts, 2) if total_appts else 0.0,
            "booked_minutes": round(row["booked_minutes"], 2),
            "available_minutes": round(slot_minutes, 2),
            "load_percent": round(row["booked_minutes"] * 100 / slot_minutes, 2) if slot_minutes else 0.0,
        })
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "items": result}
