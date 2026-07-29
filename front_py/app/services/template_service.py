from fastapi import Request
from fastapi.templating import Jinja2Templates


class TemplateService:
    """ห่อหุ้มการ render HTML ไม่ให้ router ผูกติดกับ Jinja2 โดยตรง
    ถ้า starlette เปลี่ยน signature อีกในอนาคต แก้ที่คลาสนี้ที่เดียว
    """

    def __init__(self, directory: str):
        self.templates = Jinja2Templates(directory=directory)

    def render(self, request: Request, name: str, context: dict | None = None):
        return self.templates.TemplateResponse(request, name, context or {})
