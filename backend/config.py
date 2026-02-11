from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_service_key: str

    # Orange Money / MyZaka
    orange_money_api_key: str = ""
    orange_money_merchant_id: str = ""
    orange_money_api_url: str = "https://api.orange.com/orange-money-webpay/mw/v1"

    # App
    secret_key: str
    whatsapp_number: str = "26777625997"
    frontend_url: str = "http://localhost:3000"
    subscription_duration_days: int = 30

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
