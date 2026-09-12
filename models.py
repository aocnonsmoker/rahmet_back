import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

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


class Trainer(Base):
    __tablename__ = "trainers"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False)  # club-template section key
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False)
    label = Column(String, nullable=False)
    color = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    kind = Column(String, nullable=False, default="group")  # "group" | "room" (club-template rooms)


class TrainerResource(Base):
    __tablename__ = "trainer_resources"
    __table_args__ = (UniqueConstraint("trainer_id", "resource_id", name="uq_trainer_resources"),)

    id = Column(Integer, primary_key=True, nullable=False)
    trainer_id = Column(Integer, ForeignKey("trainers.id"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)  # group


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
    guest_fields = Column(String, nullable=False, default="none")  # "none" | "single" | "split" — time_slot template only


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


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False, index=True)  # club-template section key this client's card belongs to
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    parent_name = Column(String, nullable=True)  # guardian name, for minor clients
    contract_number = Column(String, nullable=True)
    contract_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    section = Column(String, nullable=False)  # club-template section key
    payment_date = Column(DateTime, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    price = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="active")  # "active" | "expired" | "frozen"


class GroupSchedule(Base):
    __tablename__ = "group_schedules"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    section = Column(String, nullable=False, index=True)  # club-template section key
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)  # группа
    room_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)  # зал (kind="room")
    # [{"day": 0-6 (0=Пн..6=Вс), "start_time": "HH:MM", "end_time": "HH:MM"}, ...] —
    # each day of the week can have its own time range (e.g. Пн 16:00, Ср 18:00).
    day_times = Column(JSONB, nullable=False)


class MembershipResource(Base):
    __tablename__ = "membership_resources"
    __table_args__ = (UniqueConstraint("membership_id", "resource_id", name="uq_membership_resources"),)

    id = Column(Integer, primary_key=True, nullable=False)
    membership_id = Column(Integer, ForeignKey("memberships.id"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)  # group


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("membership_id", "date", name="uq_attendance_membership_date"),)

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    membership_id = Column(Integer, ForeignKey("memberships.id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    status = Column(String, nullable=False)  # "present" | "absent"


class TrialLesson(Base):
    __tablename__ = "trial_lessons"

    id = Column(Integer, primary_key=True, nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    section = Column(String, nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)  # group, if known yet
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="scheduled")
    # "scheduled" | "came" | "no_show" | "bought" | "thinking" | "declined"
    created_at = Column(DateTime, server_default=func.now())
