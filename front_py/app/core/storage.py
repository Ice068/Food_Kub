import os
import uuid
import httpx

async def upload_image_to_cloud(file_content: bytes, original_filename: str) -> str | None:
    """
    อัปโหลดรูปภาพขึ้น Cloud Server (Catbox Cloud Storage) ฟรี โดยไม่ต้องผูกบัตรเครดิต
    จะได้รับ Public Direct URL ถาวร (เช่น https://files.catbox.moe/xxxx.jpg)
    """
    try:
        ext = os.path.splitext(original_filename)[1] or ".jpg"
        clean_filename = f"{uuid.uuid4().hex[:8]}{ext}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (clean_filename, file_content)},
                timeout=20.0
            )
            
            if response.status_code == 200 and response.text.startswith("http"):
                direct_url = response.text.strip()
                print(f"[Cloud Storage] อัปโหลดรูปภาพสำเร็จ: {direct_url}")
                return direct_url
            else:
                print(f"[Cloud Storage Error] Response: {response.text}")
                return None
    except Exception as e:
        print(f"[Cloud Storage Exception]: {e}")
        return None
