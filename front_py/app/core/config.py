class Settings:
  """เก็บค่า config ของระบบ"""
  APP_TITLE: str = "ระบบสั่งร้านอาหาร"
  TEMPLATES_DIR: str = "templates"
  STATIC_DIR: str = "static"
  STATIC_URL: str = "/static"
  BACKEND_URL: str = "http://localhost:8000"


settings = Settings()