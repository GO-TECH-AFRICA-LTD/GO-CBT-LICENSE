import os

class Settings:
    SECRET_KEY = os.environ.get("APP_SECRET", "change_this_in_render_env")
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    PRODUCT_CODE = os.environ.get("PRODUCT_CODE", "gocbt-desktop")
    MAX_DEVICES = int(os.environ.get("MAX_DEVICES", "1"))

settings = Settings()
