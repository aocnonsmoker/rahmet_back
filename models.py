import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint, func

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)
    status = Column(String, nullable=False, default="trial")
    expires_at = Column(DateTime, nullable=False)
    notes = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),)

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "owner" | "employee"
    is_active = Column(Boolean, nullable=False, default=True)
    read_only = Column(Boolean, nullable=False, default=False)  # can view assigned sections but not add/edit/delete
    created_at = Column(DateTime, server_default=func.now())


class UserSection(Base):
    __tablename__ = "user_sections"
    __table_args__ = (UniqueConstraint("user_id", "section", name="uq_user_sections_user_section"),)

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    section = Column(String, nullable=False)  # "spa" | "car" | "hotel" | "ps"


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False)
    label = Column(String, nullable=False)
    color = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_sections_tenant_key"),)

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    icon = Column(String, nullable=False)  # emoji
    template = Column(String, nullable=False)  # "time_slot" | "date_range" | "queue"
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    slot_step_minutes = Column(Integer, nullable=False, default=30)  # time_slot template only


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)
    title = Column(String, nullable=False)
    price = Column(Integer, nullable=True)
    start = Column(DateTime, index=True)
    end = Column(DateTime, index=True, nullable=True)
    adult = Column(Integer, nullable=True)
    child = Column(Integer, nullable=True)
