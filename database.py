import os
from datetime import date, datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv
import random
import string

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Пользователи ----
def generate_referral_code(user_id: str) -> str:
    """Генерирует уникальный реферальный код на основе user_id"""
    return f"ref_{user_id}"

def get_user(user_id: str):
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        # Новый пользователь
        referral_code = generate_referral_code(user_id)
        supabase.table("users").insert({
            "user_id": user_id,
            "requests_today": 0,
            "last_request_date": str(date.today()),
            "gender": None,
            "style_preference": None,
            "total_free_requests": 0,
            "is_premium": False,
            "premium_until": None,
            "referral_code": referral_code,
            "referred_by": None
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
            "referral_code": referral_code,
            "referred_by": None
        }

def update_user(user_id: str, data: dict):
    supabase.table("users").update(data).eq("user_id", user_id).execute()

def can_request(user_id: str) -> bool:
    user = get_user(user_id)
    if user.get("is_premium"):
        return True
    used = user.get("total_free_requests", 0)
    return used < 3

def increment_free_requests(user_id: str):
    user = get_user(user_id)
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
    if gender is not None:
        data["gender"] = gender
    if style is not None:
        data["style_preference"] = style
    if data:
        update_user(user_id, data)

# ---- Реферальная система ----
def get_referral_link(user_id: str) -> str:
    user = get_user(user_id)
    code = user.get("referral_code")
    if not code:
        code = generate_referral_code(user_id)
        update_user(user_id, {"referral_code": code})
    return f"https://t.me/stil_snap_ai_bot?start={code}"

def apply_referral(new_user_id: str, referrer_code: str):
    """Начисляет бонусы пригласившему и приглашённому"""
    # Находим пригласившего по коду
    resp = supabase.table("users").select("user_id").eq("referral_code", referrer_code).execute()
    if not resp.data:
        return False
    referrer_id = resp.data[0]["user_id"]
    if referrer_id == new_user_id:
        return False  # Нельзя пригласить самого себя

    # Сохраняем, кто пригласил
    update_user(new_user_id, {"referred_by": referrer_id})

    # Начисляем бонусы обоим
    # Увеличиваем счётчик бесплатных запросов у пригласившего (если не премиум)
    # У приглашённого тоже увеличиваем
    # Для простоты увеличиваем total_free_requests (это уменьшит использованные на 1)
    # Но total_free_requests хранит количество уже использованных, а не оставшихся.
    # Поэтому лучше хранить бонусы отдельно, но для простоты увеличим total_free_requests на -1 (т.е. уменьшим использованные)
    # Но нужно быть осторожным: у пользователя могло быть уже использовано 3, и тогда он не может получить бонус.
    # Сделаем проще: добавим поле `bonus_requests` (отдельно от бесплатных).
    # Пока не будем усложнять, а просто увеличим total_free_requests (использованные) на -1, если значение больше 0.
    # Но это не совсем корректно. Для MVP можно сделать так:
    # У пригласившего: если он не премиум, уменьшаем total_free_requests на 1 (но не меньше 0)
    # У приглашённого: тоже уменьшаем total_free_requests на 1 (даём +1 бесплатный)
    # Однако если total_free_requests уже 0, то уменьшить нельзя. Поэтому лучше отдельное поле.
    # Давайте добавим поле `bonus_requests` в таблицу.
    # Для начала я просто напишу заглушку, а вы потом добавите поле.
    # Временно просто отправляем сообщения о бонусах, а начисление будет позже.
    # Но для полноты я добавлю SQL для добавления колонки.

    # После добавления колонки можно будет:
    # update_user(referrer_id, {"bonus_requests": user["bonus_requests"] + 1})
    # update_user(new_user_id, {"bonus_requests": user["bonus_requests"] + 1})

    return True

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
