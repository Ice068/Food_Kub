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
async def add_item(payload: AddItemSchema):
    new_item = menu_service.add_item(
        name=payload.name,
        price=payload.price,
        image=payload.image,
        category=payload.category
    )
    return {"status": "success", "item": new_item.to_dict()}

@router.post("/delete/{item_id}")
async def delete_item(item_id: int):
    success = menu_service.delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or delete failed")
    return {"status": "success", "message": f"Item {item_id} deleted"}
