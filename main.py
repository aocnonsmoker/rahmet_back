from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.params import Body
from fastapi.middleware.cors import CORSMiddleware
from models import Events, Car
import models
from pydantic import BaseModel
from models import SessionLocal
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Accept requests from any origin
    allow_credentials=True,  # Allow cookies and authentication
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

models.Base.metadata.create_all(bind=models.engine)

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get('/events')
async def get_events():
    db = SessionLocal()
    item = db.query(Events).all()
    db.close()
    return item


@app.post('/record')
def record(event: dict = Body(...)):
    db = SessionLocal()
    db_item = Events(title=event['title'], adult=event['adult'], child=event['child'],
                     split=event['split'], price=event['price'], start=event['start'], end=event['end'],
                     duration=event['duration'])
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return 'Запись добавлена'


class EventUpdate(BaseModel):
    title: str
    adult: Optional[int] = None
    child: Optional[int] = None
    price: Optional[int] = None
    start: str
    end: str
    split: int


@app.put('/events/{item_id}')
async def update_item(item_id: int, event: EventUpdate):
    db = SessionLocal()
    db_item = db.query(Events).filter(Events.id == item_id).first()

    if db_item is None:
        return {"error": "Event not found"}

    db_item.title = event.title
    db_item.adult = event.adult
    db_item.child = event.child
    db_item.price = event.price
    db_item.start = event.start
    db_item.end = event.end
    db_item.split = event.split
    db.commit()
    db.close()

    return "Запись отредактирована"

'3.121.29.84'


@app.delete('/events/{item_id}')
async def delete_item(item_id: int):
    db = SessionLocal()
    db_item = db.query(Events).filter(Events.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Запись удалена"



@app.get('/car')
async def get_car():
    db = SessionLocal()
    item = db.query(Car).all()
    db.close()
    return item


@app.post('/record-car')
def record(car: dict = Body(...)):
    db = SessionLocal()
    db_item = Car(title=car['title'], price=car['price'], start=car['start'])
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return 'Запись добавлена'


class CarUpdate(BaseModel):
    title: str
    price: Optional[int] = None
    start: str


@app.put('/car/{item_id}')
async def update_item(item_id: int, car: CarUpdate):
    db = SessionLocal()
    db_item = db.query(Car).filter(Car.id == item_id).first()

    if db_item is None:
        return {"error": "Event not found"}

    db_item.title = car.title
    db_item.price = car.price
    db_item.start = car.start
    db.commit()
    db.close()

    return "Запись отредактирована"


@app.delete('/car/{item_id}')
async def delete_item(item_id: int):
    db = SessionLocal()
    db_item = db.query(Car).filter(Car.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Запись удалена"