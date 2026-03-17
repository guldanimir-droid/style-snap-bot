import os
from datetime import date
from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

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
