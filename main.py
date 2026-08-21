import os
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.params import Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models import Events, Car, PS, Hotel, MenuCategory, MenuItem, RestaurantOrder, RestaurantOrderItem
import models
from pydantic import BaseModel
from models import SessionLocal
from typing import List, Optional, Tuple

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Accept requests from any origin
    allow_credentials=True,  # Allow cookies and authentication
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

models.Base.metadata.create_all(bind=models.engine)

UPLOAD_DIR = "uploads"
MENU_PHOTO_DIR = os.path.join(UPLOAD_DIR, "menu")
os.makedirs(MENU_PHOTO_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")


def save_menu_photo(photo: UploadFile) -> str:
    ext = os.path.splitext(photo.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(MENU_PHOTO_DIR, filename), "wb") as f:
        f.write(photo.file.read())
    return f"menu/{filename}"

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


@app.get('/ps')
async def get_ps():
    db = SessionLocal()
    item = db.query(PS).all()
    db.close()
    return item


@app.post('/record-ps')
def record(ps: dict = Body(...)):
    db = SessionLocal()
    db_item = PS(title=ps['title'], price=ps['price'], start=ps['start'])
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return 'Запись добавлена'


class PSUpdate(BaseModel):
    title: str
    price: Optional[int] = None
    start: str


@app.put('/ps/{item_id}')
async def update_item(item_id: int, ps: PSUpdate):
    db = SessionLocal()
    db_item = db.query(PS).filter(PS.id == item_id).first()

    if db_item is None:
        return {"error": "Event not found"}

    db_item.title = ps.title
    db_item.price = ps.price
    db_item.start = ps.start
    db.commit()
    db.close()

    return "Запись отредактирована"


@app.delete('/ps/{item_id}')
async def delete_item(item_id: int):
    db = SessionLocal()
    db_item = db.query(PS).filter(PS.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Запись удалена"


@app.get('/hotel')
async def get_hotel():
    db = SessionLocal()
    item = db.query(Hotel).all()
    db.close()
    return item


@app.post('/record-hotel')
def record_hotel(hotel: dict = Body(...)):
    db = SessionLocal()
    db_item = Hotel(title=hotel['title'], split=hotel['split'], price=hotel['price'],
                    start=hotel['start'], end=hotel['end'])
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return 'Запись добавлена'


class HotelUpdate(BaseModel):
    title: str
    price: Optional[int] = None
    start: str
    end: str
    split: int


@app.put('/hotel/{item_id}')
async def update_hotel(item_id: int, hotel: HotelUpdate):
    db = SessionLocal()
    db_item = db.query(Hotel).filter(Hotel.id == item_id).first()

    if db_item is None:
        return {"error": "Hotel not found"}

    db_item.title = hotel.title
    db_item.price = hotel.price
    db_item.start = hotel.start
    db_item.end = hotel.end
    db_item.split = hotel.split
    db.commit()
    db.close()

    return "Запись отредактирована"


@app.delete('/hotel/{item_id}')
async def delete_hotel(item_id: int):
    db = SessionLocal()
    db_item = db.query(Hotel).filter(Hotel.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Запись удалена"


# ============================== Меню (категории) ==============================

@app.get('/menu-categories')
async def get_menu_categories():
    db = SessionLocal()
    items = db.query(MenuCategory).order_by(MenuCategory.sort_order).all()
    db.close()
    return items


@app.post('/menu-categories')
def create_menu_category(category: dict = Body(...)):
    db = SessionLocal()
    db_item = MenuCategory(label=category['label'], sort_order=category.get('sort_order', 0))
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    db.close()
    return 'Категория добавлена'


class MenuCategoryUpdate(BaseModel):
    label: str
    sort_order: int = 0


@app.put('/menu-categories/{item_id}')
async def update_menu_category(item_id: int, category: MenuCategoryUpdate):
    db = SessionLocal()
    db_item = db.query(MenuCategory).filter(MenuCategory.id == item_id).first()

    if db_item is None:
        db.close()
        return {"error": "Category not found"}

    db_item.label = category.label
    db_item.sort_order = category.sort_order
    db.commit()
    db.close()

    return "Категория отредактирована"


@app.delete('/menu-categories/{item_id}')
async def delete_menu_category(item_id: int):
    db = SessionLocal()
    db.query(MenuItem).filter(MenuItem.category_id == item_id).delete()
    db_item = db.query(MenuCategory).filter(MenuCategory.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Категория удалена"


# ============================== Меню (блюда) ==============================

@app.get('/menu-items')
async def get_menu_items():
    db = SessionLocal()
    items = db.query(MenuItem).order_by(MenuItem.category_id, MenuItem.sort_order).all()
    db.close()
    return items


@app.post('/menu-items')
async def create_menu_item(
    category_id: int = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    price: Optional[int] = Form(None),
    tag: Optional[str] = Form(None),
    is_available: bool = Form(True),
    sort_order: int = Form(0),
    photo: Optional[UploadFile] = File(None),
):
    db = SessionLocal()
    db_item = MenuItem(
        category_id=category_id,
        name=name,
        description=description,
        price=price,
        tag=tag,
        is_available=is_available,
        sort_order=sort_order,
        photo_path=save_menu_photo(photo) if photo is not None else None,
    )
    db.add(db_item)
    db.commit()
    db.close()
    return 'Блюдо добавлено'


@app.put('/menu-items/{item_id}')
async def update_menu_item(
    item_id: int,
    category_id: int = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    price: Optional[int] = Form(None),
    tag: Optional[str] = Form(None),
    is_available: bool = Form(True),
    sort_order: int = Form(0),
    photo: Optional[UploadFile] = File(None),
):
    db = SessionLocal()
    db_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()

    if db_item is None:
        db.close()
        return {"error": "Item not found"}

    db_item.category_id = category_id
    db_item.name = name
    db_item.description = description
    db_item.price = price
    db_item.tag = tag
    db_item.is_available = is_available
    db_item.sort_order = sort_order
    if photo is not None:
        db_item.photo_path = save_menu_photo(photo)
    db.commit()
    db.close()

    return "Блюдо отредактировано"


@app.delete('/menu-items/{item_id}')
async def delete_menu_item(item_id: int):
    db = SessionLocal()
    db_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    db.delete(db_item)
    db.commit()
    db.close()
    return "Блюдо удалено"


# ============================== Меню (публичная страница по QR) ==============================

@app.get('/menu')
async def get_public_menu():
    db = SessionLocal()
    categories = db.query(MenuCategory).order_by(MenuCategory.sort_order).all()
    result = []
    for category in categories:
        items = (
            db.query(MenuItem)
            .filter(MenuItem.category_id == category.id, MenuItem.is_available == True)  # noqa: E712
            .order_by(MenuItem.sort_order)
            .all()
        )
        if not items:
            continue
        result.append({
            "id": category.id,
            "label": category.label,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "photo_path": item.photo_path,
                    "tag": item.tag,
                }
                for item in items
            ],
        })
    db.close()
    return result


# ============================== Заказы официанта ==============================

class OrderItemIn(BaseModel):
    menu_item_id: int
    qty: int


class OrderIn(BaseModel):
    table_label: Optional[str] = None
    start: str
    items: List[OrderItemIn]


def build_order_items(db, items: List[OrderItemIn]) -> Tuple[List[RestaurantOrderItem], int]:
    order_items = []
    total = 0
    for entry in items:
        if entry.qty <= 0:
            continue
        menu_item = db.query(MenuItem).filter(MenuItem.id == entry.menu_item_id).first()
        if menu_item is None:
            continue
        order_items.append(RestaurantOrderItem(
            menu_item_id=menu_item.id,
            name=menu_item.name,
            price=menu_item.price or 0,
            qty=entry.qty,
        ))
        total += (menu_item.price or 0) * entry.qty
    return order_items, total


@app.get('/restaurant-orders')
async def get_restaurant_orders():
    db = SessionLocal()
    orders = db.query(RestaurantOrder).order_by(RestaurantOrder.start.desc()).all()
    result = []
    for order in orders:
        items = db.query(RestaurantOrderItem).filter(RestaurantOrderItem.order_id == order.id).all()
        result.append({
            "id": order.id,
            "table_label": order.table_label,
            "price": order.price,
            "start": order.start,
            "items": [
                {"id": i.id, "menu_item_id": i.menu_item_id, "name": i.name, "price": i.price, "qty": i.qty}
                for i in items
            ],
        })
    db.close()
    return result


@app.post('/restaurant-orders')
def create_restaurant_order(order: OrderIn):
    db = SessionLocal()
    order_items, total = build_order_items(db, order.items)
    db_order = RestaurantOrder(table_label=order.table_label, price=total, start=order.start)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    for item in order_items:
        item.order_id = db_order.id
        db.add(item)
    db.commit()
    db.close()
    return 'Заказ добавлен'


@app.put('/restaurant-orders/{item_id}')
def update_restaurant_order(item_id: int, order: OrderIn):
    db = SessionLocal()
    db_order = db.query(RestaurantOrder).filter(RestaurantOrder.id == item_id).first()

    if db_order is None:
        db.close()
        return {"error": "Order not found"}

    db.query(RestaurantOrderItem).filter(RestaurantOrderItem.order_id == item_id).delete()

    order_items, total = build_order_items(db, order.items)
    db_order.table_label = order.table_label
    db_order.start = order.start
    db_order.price = total
    for item in order_items:
        item.order_id = db_order.id
        db.add(item)
    db.commit()
    db.close()

    return "Заказ отредактирован"


@app.delete('/restaurant-orders/{item_id}')
async def delete_restaurant_order(item_id: int):
    db = SessionLocal()
    db.query(RestaurantOrderItem).filter(RestaurantOrderItem.order_id == item_id).delete()
    db_order = db.query(RestaurantOrder).filter(RestaurantOrder.id == item_id).first()
    db.delete(db_order)
    db.commit()
    db.close()
    return "Заказ удалён"
    db.close()
    return result