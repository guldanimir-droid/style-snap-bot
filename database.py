import os
from datetime import date, datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Пользователи ----
def generate_referral_code(user_id: str) -> str:
    return f"ref_{user_id}"

def get_user(user_id: str):
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    else:
        referral_code = generate_referral_code(user_id)
        supabase.table("users").insert({
            "user_id": user_id,
            "gender": None,
            "style_preference": None,
            "total_free_requests": 0,      # сколько использовано из 3 базовых
            "bonus_requests": 0,           # бонусные (рефералы, приветственные)
            "paid_requests": 0,            # купленные за деньги
            "referral_code": referral_code,
            "referred_by": None,
            "welcome_bonus_granted": False,
            "last_bonus_date": None        # не используется, но оставим
        }).execute()
        return {
            "user_id": user_id,
            "gender": None,
            "style_preference": None,
            "total_free_requests": 0,
            "bonus_requests": 0,
            "paid_requests": 0,
            "referral_code": referral_code,
            "referred_by": None,
            "welcome_bonus_granted": False,
            "last_bonus_date": None
        }

def update_user(user_id: str, data: dict):
    supabase.table("users").update(data).eq("user_id", user_id).execute()

def can_request(user_id: str) -> bool:
    user = get_user(user_id)
    used_free = user.get("total_free_requests", 0)
    bonus = user.get("bonus_requests", 0)
    paid = user.get("paid_requests", 0)
    # Доступно: неиспользованные бесплатные (3 - used_free) + бонусы + платные
    remaining_free = max(0, 3 - used_free)
    return (remaining_free + bonus + paid) > 0

def use_request(user_id: str):
    """Списывает один запрос в порядке: бонусы, потом платные, потом бесплатные."""
    user = get_user(user_id)
    bonus = user.get("bonus_requests", 0)
    paid = user.get("paid_requests", 0)
    used_free = user.get("total_free_requests", 0)
    if bonus > 0:
        update_user(user_id, {"bonus_requests": bonus - 1})
    elif paid > 0:
        update_user(user_id, {"paid_requests": paid - 1})
    else:
        # списываем из бесплатных (но не более 3)
        if used_free < 3:
            update_user(user_id, {"total_free_requests": used_free + 1})
        else:
            # на всякий случай, хотя can_request не пропустит
            pass

def add_paid_analysis(user_id: str):
    """Начисляет 1 платный анализ после успешной оплаты."""
    user = get_user(user_id)
    current = user.get("paid_requests", 0)
    update_user(user_id, {"paid_requests": current + 1})

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
    resp = supabase.table("users").select("user_id").eq("referral_code", referrer_code).execute()
    if not resp.data:
        return False
    referrer_id = resp.data[0]["user_id"]
    if referrer_id == new_user_id:
        return False
    new_user = get_user(new_user_id)
    if new_user.get("referred_by"):
        return False
    update_user(new_user_id, {"referred_by": referrer_id})
    referrer = get_user(referrer_id)
    new_bonus_ref = referrer.get("bonus_requests", 0) + 1
    update_user(referrer_id, {"bonus_requests": new_bonus_ref})
    new_bonus_new = new_user.get("bonus_requests", 0) + 1
    update_user(new_user_id, {"bonus_requests": new_bonus_new})
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

def delete_favorite(user_id: str, favorite_id: int):
    supabase.table("favorites").delete().eq("id", favorite_id).eq("user_id", user_id).execute()
