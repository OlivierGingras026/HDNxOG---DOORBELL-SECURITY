# models.py
from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.sql import func
from db import Base


class EnvironmentData(Base):
    __tablename__ = "environment_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    temperature = Column(Float)
    humidity = Column(Float)
    pressure = Column(Float)


class MotionEvent(Base):
    __tablename__ = "motion_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), index=True)

    image_path = Column(String, nullable=True)
