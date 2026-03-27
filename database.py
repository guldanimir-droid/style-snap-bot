import os
from datetime import date, datetime, timedelta
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
    """Возвращает пользователя, создаёт если не существует"""
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        # Новый пользователь: 0 использованных бесплатных запросов, не премиум
        supabase.table("users").insert({
            "user_id": user_id,
            "requests_today": 0,               # можно оставить для совместимости
            "last_request_date": str(date.today()),
            "gender": None,
            "style_preference": None,
            "city": None,
            "total_free_requests": 0,
            "is_premium": False,
            "premium_until": None
        }).execute()
        return {
            "user_id": user_id,
            "requests_today": 0,
            "last_request_date": str(date.today()),
            "gender": None,
            "style_preference": None,
            "city": None,
            "total_free_requests": 0,
            "is_premium": False,
            "premium_until": None
        }

def update_user(user_id: str, data: dict):
    supabase.table("users").update(data).eq("user_id", user_id).execute()

def can_request(user_id: str) -> bool:
    """
    Проверяет, может ли пользователь сделать бесплатный запрос:
    - если премиум – всегда может
    - если нет – total_free_requests < 3
    """
    user = get_user(user_id)
    if user.get("is_premium"):
        return True
    return user.get("total_free_requests", 0) < 3

def increment_free_requests(user_id: str):
    """Увеличивает счётчик использованных бесплатных запросов"""
    user = get_user(user_id)
    new_count = user.get("total_free_requests", 0) + 1
    update_user(user_id, {"total_free_requests": new_count})

def is_premium(user_id: str) -> bool:
    """Проверяет, активна ли подписка (учитывая дату окончания)"""
    user = get_user(user_id)
    if not user.get("is_premium"):
        return False
    premium_until = user.get("premium_until")
    if premium_until:
        if datetime.fromisoformat(premium_until.replace('Z', '+00:00')) < datetime.now().astimezone():
            # срок истёк
            update_user(user_id, {"is_premium": False, "premium_until": None})
            return False
    return True

def set_premium(user_id: str, duration_days: int = 30):
    """Устанавливает премиум-статус на указанное количество дней"""
    premium_until = datetime.now() + timedelta(days=duration_days)
    update_user(user_id, {
        "is_premium": True,
        "premium_until": premium_until.isoformat()
    })

# ---- Гардероб ----

def add_wardrobe_item(user_id: str, item_name: str, category: str = None, color: str = None, image_url: str = None):
    supabase.table("wardrobe").insert({
        "user_id": user_id,
        "item_name": item_name,
        "category": category,
        "color": color,
        "image_url": image_url
    }).execute()

def get_user_wardrobe(user_id: str):
    response = supabase.table("wardrobe").select("*").eq("user_id", user_id).execute()
    return response.data

def delete_wardrobe_item(item_id: int):
    supabase.table("wardrobe").delete().eq("id", item_id).execute()

# ---- Избранное ----

def add_favorite(user_id: str, result_text: str):
    supabase.table("favorites").insert({
        "user_id": user_id,
        "result_text": result_text
    }).execute()

def get_favorites(user_id: str):
    response = supabase.table("favorites").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return response.data

def delete_favorite(favorite_id: int):
    supabase.table("favorites").delete().eq("id", favorite_id).execute()
