from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey

SQLALCHEMY_DATABASE_URL = 'postgresql://postgres:nonsmoker123@localhost:5432/postgres'
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Events(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    adult = Column(Integer, nullable=True)
    child = Column(Integer, nullable=True)
    split = Column(Integer, nullable=False)
    price = Column(Integer, nullable=True)
    start = Column(DateTime, index=True)
    end = Column(DateTime, index=True)
    duration = Column(Float, nullable=False)


class Car(Base):
    __tablename__ = "car"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    price = Column(Integer, nullable=True)
    start = Column(DateTime, index=True)

class PS(Base):
    __tablename__ = "ps"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    price = Column(Integer, nullable=True)
    start = Column(DateTime, index=True)

class Hotel(Base):
    __tablename__ = "hotel"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    split = Column(Integer, nullable=False)
    price = Column(Integer, nullable=True)
    start = Column(DateTime, index=True)
    end = Column(DateTime, index=True)


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id = Column(Integer, primary_key=True, nullable=False)
    label = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, nullable=False)
    category_id = Column(Integer, ForeignKey("menu_categories.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    photo_path = Column(String, nullable=True)
    tag = Column(String, nullable=True)  # short badge, e.g. "вег." / "острое"
    is_available = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)


class RestaurantOrder(Base):
    __tablename__ = "restaurant_orders"

    id = Column(Integer, primary_key=True, nullable=False)
    table_label = Column(String, nullable=True)
    price = Column(Integer, nullable=False, default=0)
    start = Column(DateTime, index=True)


class RestaurantOrderItem(Base):
    __tablename__ = "restaurant_order_items"

    id = Column(Integer, primary_key=True, nullable=False)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    qty = Column(Integer, nullable=False, default=1)