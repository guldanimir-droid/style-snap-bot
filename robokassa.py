import hashlib
import os
import time
from urllib.parse import urlencode
import database  # ваш модуль работы с Supabase

async def generate_payment_link(user_id: str, amount: float, description: str) -> str:
    """Создаёт счёт в БД, генерирует ссылку на оплату Robokassa."""
    # Сохраняем счёт в БД, получаем его ID
    invoice_id = database.create_invoice(user_id, amount, description)  # функция ниже
    login = os.getenv('ROBOKASSA_LOGIN')
    password1 = os.getenv('ROBOKASSA_PASSWORD1')
    is_test = int(os.getenv('ROBOKASSA_TEST', 1)) == 1
    data = {
        'MerchantLogin': login,
        'OutSum': f"{amount:.2f}",
        'InvId': invoice_id,
        'Description': description,
        'SignatureValue': hashlib.md5(f"{login}:{amount:.2f}:{invoice_id}:{password1}".encode()).hexdigest(),
        'IsTest': 1 if is_test else 0,
    }
    base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
    return f"{base_url}?{urlencode(data)}"

def check_result_signature(params: dict) -> bool:
    """Проверяет подпись уведомления Result URL (пароль #2)"""
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    out_sum = params.get('OutSum')
    inv_id = params.get('InvId')
    signature = params.get('SignatureValue')
    if not all([out_sum, inv_id, signature]):
        return False
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    return my_signature == signature.upper()

def add_analyses_by_invoice(invoice_id: int, amount: float) -> bool:
    """Начисляет анализы пользователю по оплаченному счету"""
    invoice = database.get_invoice(invoice_id)
    if not invoice or invoice['status'] != 'pending':
        return False
    user_id = invoice['user_id']
    if amount == 25.0:
        analyses = 1
    elif amount == 50.0:
        analyses = 3
    elif amount == 75.0:
        analyses = 5
    elif amount == 500.0:
        analyses = 999  # подписка, но пока просто много
    else:
        return False
    for _ in range(analyses):
        database.add_paid_analysis(user_id)
    database.update_invoice_status(invoice_id, 'paid')
    return True
