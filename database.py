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
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        supabase.table("users").insert({
            "user_id": user_id,
            "requests_today": 0,
            "last_request_date": str(date.today()),
            "gender": None,
            "style_preference": None,
            "total_free_requests": 0,
            "is_premium": False,
            "premium_until": None,
            "bonus_requests": 0,
            "referrer": None
        }).execute()
        return {
            "user_id": user_id,
            "requests_today": 0,
            "last_request_date": str(date.today()),
            "gender": None,
            "style_preference": None,
            "total_free_requests": 0,
            "is_premium": False,
            "premium_until": None,
            "bonus_requests": 0,
            "referrer": None
        }

def update_user(user_id: str, data: dict):
    supabase.table("users").update(data).eq("user_id", user_id).execute()

def can_request(user_id: str) -> bool:
    """Проверяет, может ли пользователь сделать бесплатный запрос:
       - если премиум – всегда может
       - иначе: (3 - total_free_requests) + bonus_requests > 0
    """
    user = get_user(user_id)
    if user.get("is_premium"):
        return True
    remaining_free = 3 - user.get("total_free_requests", 0)
    remaining_bonus = user.get("bonus_requests", 0)
    return (remaining_free + remaining_bonus) > 0

def increment_free_requests(user_id: str):
    """
    Увеличивает счётчик использованных бесплатных запросов (сначала списывает бонусы, потом бесплатные)
    """
    user = get_user(user_id)
    if user.get("is_premium"):
        return
    bonus = user.get("bonus_requests", 0)
    if bonus > 0:
        # списываем бонус
        update_user(user_id, {"bonus_requests": bonus - 1})
    else:
        new_count = user.get("total_free_requests", 0) + 1
        update_user(user_id, {"total_free_requests": new_count})

def is_premium(user_id: str) -> bool:
    user = get_user(user_id)
    if not user.get("is_premium"):
        return False
    premium_until = user.get("premium_until")
    if premium_until:
        if datetime.fromisoformat(premium_until.replace('Z', '+00:00')) < datetime.now().astimezone():
            update_user(user_id, {"is_premium": False, "premium_until": None})
            return False
    return True

def set_premium(user_id: str, duration_days: int = 30):
    premium_until = datetime.now() + timedelta(days=duration_days)
    update_user(user_id, {
        "is_premium": True,
        "premium_until": premium_until.isoformat()
    })

def set_user_info(user_id: str, gender: str = None, style: str = None):
    data = {}
    if gender:
        data["gender"] = gender
    if style:
        data["style_preference"] = style
    if data:
        update_user(user_id, data)

def add_bonus_requests(user_id: str, amount: int = 1):
    """Добавляет бонусные запросы пользователю"""
    user = get_user(user_id)
    new_bonus = user.get("bonus_requests", 0) + amount
    update_user(user_id, {"bonus_requests": new_bonus})

def set_referrer(user_id: str, referrer_id: str):
    """Сохраняет, кто пригласил пользователя"""
    user = get_user(user_id)
    if user.get("referrer") is None:
        update_user(user_id, {"referrer": referrer_id})
        # начисляем бонус пригласившему
        add_bonus_requests(referrer_id, amount=1)

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
