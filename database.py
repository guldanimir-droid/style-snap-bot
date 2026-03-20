import os
from datetime import date
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Пользователи ----

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

# ---- Гардероб ----

def add_wardrobe_item(user_id: str, item_name: str, category: str = None, color: str = None, image_url: str = None):
    """Добавляет вещь в гардероб пользователя"""
    supabase.table("wardrobe").insert({
        "user_id": user_id,
        "item_name": item_name,
        "category": category,
        "color": color,
        "image_url": image_url
    }).execute()

def get_user_wardrobe(user_id: str):
    """Возвращает все вещи пользователя"""
    response = supabase.table("wardrobe").select("*").eq("user_id", user_id).execute()
    return response.data

def delete_wardrobe_item(item_id: int):
    """Удаляет вещь по id (можно добавить позже)"""
    supabase.table("wardrobe").delete().eq("id", item_id).execute()
