from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Float

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