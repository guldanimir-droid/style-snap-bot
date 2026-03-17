import os
from datetime import date
from supabase import create_client, Client

# Отладка: выводим все переменные окружения
print("=== DEBUG: All environment variables ===")
for key, value in os.environ.items():
    # Не выводим значения ключей полностью, чтобы не засорять логи, но покажем имена
    print(f"{key} = {'set' if value else 'empty'}")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print(f"SUPABASE_URL = {SUPABASE_URL}")
print(f"SUPABASE_KEY = {'set' if SUPABASE_KEY else 'NOT SET'}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user(user_id: str):
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        supabase.table("users").insert({
            "user_id": user_id,
            "requests_today": 0,
            "last_request_date": str(date.today())
        }).execute()
        return {"user_id": user_id, "requests_today": 0, "last_request_date": str(date.today()), "gender": None, "style_preference": None, "city": None}

def update_user(user_id: str, data: dict):
    supabase.table("users").update(data).eq("user_id", user_id).execute()

def increment_requests(user_id: str):
    user = get_user(user_id)
    today = str(date.today())
    if user["last_request_date"] != today:
        update_user(user_id, {"requests_today": 1, "last_request_date": today})
        return 1
    else:
        new_count = user["requests_today"] + 1
        update_user(user_id, {"requests_today": new_count})
        return new_count

def can_request(user_id: str, limit: int = 3) -> bool:
    user = get_user(user_id)
    today = str(date.today())
    if user["last_request_date"] != today:
        return True
    return user["requests_today"] < limit

def set_user_info(user_id: str, gender: str = None, style: str = None, city: str = None):
    data = {}
    if gender:
        data["gender"] = gender
    if style:
        data["style_preference"] = style
    if city:
        data["city"] = city
    if data:
        update_user(user_id, data)
