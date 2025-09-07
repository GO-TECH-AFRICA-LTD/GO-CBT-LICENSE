from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from db import Base

class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True)
    license_key = Column(String(64), unique=True, index=True)
    product_code = Column(String(64), index=True)
    paid_reference = Column(String(128), unique=True, index=True)
    status = Column(String(32), default="active")
    machine_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    __table_args__ = (UniqueConstraint("email", "paid_reference", name="uniq_email_ref"),)
