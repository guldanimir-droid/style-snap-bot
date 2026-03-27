import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DEVELOPER_ID = os.getenv("DEVELOPER_ID")
# GigaChat credentials
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_SECRET = os.getenv("GIGACHAT_SECRET")
