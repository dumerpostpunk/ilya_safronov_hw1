from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, DB_SCHEMA


def table_args():
    return {"schema": DB_SCHEMA} if DB_SCHEMA else {}


def foreign_key(table: str) -> str:
    return f"{DB_SCHEMA}.{table}.id" if DB_SCHEMA else f"{table}.id"


class Specialist(Base):
    __tablename__ = "specialists"
    __table_args__ = table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialization: Mapped[str] = mapped_column(String(120), nullable=False)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specialist_id: Mapped[int] = mapped_column(ForeignKey(foreign_key("specialists")), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey(foreign_key("slots")), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey(foreign_key("services")), nullable=False)
    client_name: Mapped[str] = mapped_column(String(120), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
