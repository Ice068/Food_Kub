"""
ไฟล์สำหรับทดสอบ API ของระบบ Food_Kub Backend
(API Integration Test)

ทดสอบการยิง Endpoint ต่างๆ ตามที่เพื่อนต้องการ:
1. ยิงดึงรายการเมนู (GET /api/menu)
2. ยิงเพิ่มเมนูใหม่ (POST /api/admin/add)
3. ยิงดึงข้อมูลเมนูที่เพิ่งเพิ่ม (GET /api/menu/{id})
4. ยิงลบเมนูทดสอบ (POST /api/admin/delete/{id})
5. ยิงทดสอบกรณีลบเมนูที่ไม่มีอยู่จริง (คาดหวัง 404)
6. ยิงทดสอบระบบจ่ายเงินเงินสด (POST /api/payment/process)
7. ยิงทดสอบระบบจ่ายเงิน QR พร้อมเพย์ (POST /api/payment/process)

วิธีรัน:
    python test_api.py
หรือถ้ามี pytest:
    pytest test_api.py -v
"""

import sys
import os

# ป้องกันปัญหา encoding บน Windows Terminal (cp874)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# เพิ่มพาธของ blackend_py เข้ามาในระบบเพื่อให้ import app ได้
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "blackend_py"))

from fastapi.testclient import TestClient
from main import app

# สร้าง TestClient สำหรับจำลองการยิง Request เข้า FastAPI
client = TestClient(app)

# สีสำหรับแสดงผลใน Terminal
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_result(title: str, passed: bool, detail: str = ""):
    status = f"{GREEN}[PASS]{RESET}" if passed else f"{RED}[FAIL]{RESET}"
    print(f"  {status} {title}")
    if detail:
        print(f"         └─ {detail}")


def test_get_menu():
    """1. ทดสอบยิงไปดึงรายการเมนูทั้งหมด"""
    res = client.get("/api/menu")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert isinstance(data, list), "ผลลัพธ์ต้องเป็น list ของเมนู"
    assert len(data) > 0, "ต้องมีเมนูในระบบอย่างน้อย 1 รายการ"
    return len(data)


def test_get_categories():
    """2. ทดสอบยิงไปดึงหมวดหมู่อาหาร"""
    res = client.get("/api/menu/categories")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    return data


def test_add_and_delete_menu():
    """3 & 4. ทดสอบยิงไป 'เพิ่ม' เมนู และ 'ลบ' เมนู"""
    # 3.1 ยิงเพิ่มเมนูใหม่
    new_item_payload = {
        "name": "ข้าวผัดทดสอบระบบ",
        "price": 89.0,
        "image": "https://files.catbox.moe/4madnn.jpg",
        "category": "จานเดียว"
    }
    res_add = client.post("/api/admin/add", json=new_item_payload)
    assert res_add.status_code == 200, f"เพิ่มเมนูไม่สำเร็จ: {res_add.text}"
    add_data = res_add.json()
    assert add_data.get("status") == "success"
    item = add_data.get("item")
    assert item is not None
    created_id = item["id"]
    assert item["name"] == new_item_payload["name"]

    # 3.2 ยิงไปดึงเมนูที่เพิ่งเพิ่มมาเช็กว่ามีจริงในระบบ
    res_get = client.get(f"/api/menu/{created_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == created_id

    # 4.1 ยิงไปลบเมนูที่เพิ่งเพิ่ม
    res_delete = client.post(f"/api/admin/delete/{created_id}")
    assert res_delete.status_code == 200, f"ลบเมนูไม่สำเร็จ: {res_delete.text}"
    assert res_delete.json().get("status") == "success"

    # 4.2 ยิงไปเช็กซ้ำว่าลบออกไปแล้วจริง (ต้องเจอ 404 Not Found)
    res_check_deleted = client.get(f"/api/menu/{created_id}")
    assert res_check_deleted.status_code == 404, "เมนูที่ลบแล้วยังคงอยู่ในระบบ!"

    return created_id


def test_delete_non_existent():
    """5. ทดสอบยิงลบเมนูที่ไม่มีอยู่จริง (ระบบต้องแจ้งเตือน 404)"""
    res = client.post("/api/admin/delete/999999")
    assert res.status_code == 404, f"Expected 404 for non-existent item, got {res.status_code}"


def test_payment_cash():
    """6. ทดสอบยิงจ่ายเงินด้วยเงินสด"""
    payload = {
        "method": "cash",
        "amount": 120.0,
        "items": [{"id": 1, "name": "ผัดไทย", "price": 60.0, "qty": 2}]
    }
    res = client.post("/api/payment/process", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "cash"
    assert data["amount"] == 120.0


def test_payment_qr_bank():
    """7. ทดสอบยิงจ่ายเงินด้วย QR พร้อมเพย์ (ต้องสร้างรูป QR Base64 สำเร็จ)"""
    payload = {
        "method": "qr_bank",
        "amount": 250.0,
        "items": [{"id": 2, "name": "ต้มยำกุ้ง", "price": 120.0, "qty": 2}]
    }
    res = client.post("/api/payment/process", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "qr_bank"
    assert "qr_image" in data
    assert len(data["qr_image"]) > 100, "ต้องมีข้อมูลรูปภาพ QR Code Base64"


def run_all_tests():
    print(f"\n{BOLD}===================================================={RESET}")
    print(f"{BOLD}   [TEST] เริ่มการทดสอบระบบ API ของ Food_Kub Backend   {RESET}")
    print(f"{BOLD}===================================================={RESET}\n")

    tests = [
        ("1. ทดสอบดึงรายการเมนูทั้งหมด (GET /api/menu)", test_get_menu),
        ("2. ทดสอบดึงรายการหมวดหมู่ (GET /api/menu/categories)", test_get_categories),
        ("3. ทดสอบยิงเพิ่มเมนู และยิงลบเมนู (POST /api/admin/add & /delete)", test_add_and_delete_menu),
        ("4. ทดสอบความถูกต้องเมื่อลบเมนูที่ไม่มีอยู่ (คาดหวัง 404)", test_delete_non_existent),
        ("5. ทดสอบยิง API จ่ายเงินสด (POST /api/payment/process)", test_payment_cash),
        ("6. ทดสอบยิง API สร้าง QR พร้อมเพย์ (POST /api/payment/process)", test_payment_qr_bank),
    ]

    passed_count = 0

    for title, test_fn in tests:
        try:
            detail = test_fn()
            detail_str = f"สำเร็จ (ข้อมูล: {detail})" if detail is not None else "ผ่านการตรวจสอบ"
            print_result(title, True, detail_str)
            passed_count += 1
        except AssertionError as err:
            print_result(title, False, f"Assertion Error: {err}")
        except Exception as err:
            print_result(title, False, f"Error: {err}")

    print(f"\n{BOLD}===================================================={RESET}")
    if passed_count == len(tests):
        print(f"{GREEN}{BOLD}>>> การทดสอบผ่านทั้งหมด: {passed_count}/{len(tests)} รายการ! <<<{RESET}")
    else:
        print(f"{RED}{BOLD}>>> การทดสอบผ่าน: {passed_count}/{len(tests)} รายการ <<<{RESET}")
    print(f"{BOLD}===================================================={RESET}\n")


if __name__ == "__main__":
    run_all_tests()
