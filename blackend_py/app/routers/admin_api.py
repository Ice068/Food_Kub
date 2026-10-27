from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.menu_service import MenuService

router = APIRouter(prefix="/api/admin", tags=["Admin"])
menu_service = MenuService()

class AddItemSchema(BaseModel):
    name: str
    price: float
    image: str
    category: str

@router.post("/add")
def add_item(payload: AddItemSchema):
    new_item = menu_service.add_item(
        name=payload.name,
        price=payload.price,
        image=payload.image,
        category=payload.category
    )
    return {"status": "success", "item": new_item.to_dict()}

@router.post("/delete/{item_id}")
def delete_item(item_id: int):
    success = menu_service.delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or delete failed")
    return {"status": "success", "message": f"Item {item_id} deleted"}

class AvailabilitySchema(BaseModel):
    available: bool

@router.patch("/availability/{item_id}")
async def set_availability(item_id: int, payload: AvailabilitySchema):
    success = menu_service.set_availability(item_id, payload.available)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "success", "available": payload.available}
