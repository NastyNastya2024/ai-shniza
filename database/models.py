from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    remaining_generations = Column(Integer, default=0, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)

class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_id = Column(String, unique=True, index=True, nullable=False)  # id платежа из Юкассы
    status = Column(String, nullable=False)  # например "waiting_for_capture", "succeeded"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
