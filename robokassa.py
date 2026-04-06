import hashlib
import os
from urllib.parse import urlencode

async def generate_payment_link(user_id: int, amount: float, description: str, invoice_id: int) -> str:
    """
    Генерирует ссылку для оплаты через Robokassa.
    amount - сумма в рублях (например, 25.0)
    invoice_id - уникальный номер счёта (можно использовать user_id + timestamp)
    """
    login = os.getenv('ROBOKASSA_LOGIN')
    password1 = os.getenv('ROBOKASSA_PASSWORD1')
    is_test = int(os.getenv('ROBOKASSA_TEST', 1)) == 1

    # Обязательные параметры
    data = {
        'MerchantLogin': login,
        'OutSum': f"{amount:.2f}",
        'InvId': invoice_id,
        'Description': description,
        'SignatureValue': hashlib.md5(f"{login}:{amount:.2f}:{invoice_id}:{password1}".encode()).hexdigest(),
        'IsTest': 1 if is_test else 0,
    }

    # Формируем URL
    base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
    return f"{base_url}?{urlencode(data)}"

def check_signature(params: dict) -> bool:
    """
    Проверяет подпись уведомления от Robokassa (для Result URL).
    Используется пароль #2.
    """
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    out_sum = params.get('OutSum')
    inv_id = params.get('InvId')
    signature = params.get('SignatureValue')
    if not all([out_sum, inv_id, signature]):
        return False
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    return my_signature == signature.upper()
