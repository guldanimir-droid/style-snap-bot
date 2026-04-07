import hashlib
import os
import time
import json
from urllib.parse import urlencode

# Генерация ссылки для оплаты (вызывается из бота)
async def generate_payment_link(user_id: str, amount: float, description: str) -> str:
    login = os.getenv('ROBOKASSA_LOGIN')
    password1 = os.getenv('ROBOKASSA_PASSWORD1')
    is_test = int(os.getenv('ROBOKASSA_TEST', '1')) == 1

    # Уникальный номер счета (InvId)
    invoice_id = int(time.time() * 1000) % 1000000000

    # Данные для чека (обязательно для ФЗ-54)
    receipt = {
        "items": [
            {
                "name": description,
                "quantity": 1.0,
                "sum": amount,
                "tax": "none"
            }
        ]
    }
    receipt_json = json.dumps(receipt, separators=(',', ':'))

    # Пользовательский параметр (передаём ID телеграм-пользователя)
    shp_params = {'Shp_user_id': user_id}

    # Сортируем Shp-параметры по алфавиту (у нас он один)
    sorted_shp = sorted(shp_params.items())

    # Строка для подписи: логин:сумма:счет:Receipt:пароль1:Shp_ключ=значение
    signature_parts = [login, f"{amount:.2f}", str(invoice_id), receipt_json, password1]
    for k, v in sorted_shp:
        signature_parts.append(f"{k}={v}")
    signature_str = ":".join(signature_parts)
    signature_value = hashlib.md5(signature_str.encode()).hexdigest().upper()

    # Все параметры для ссылки
    data = {
        'MerchantLogin': login,
        'OutSum': f"{amount:.2f}",
        'InvId': invoice_id,
        'Description': description,
        'Receipt': receipt_json,
        'IsTest': 1 if is_test else 0,
        'SignatureValue': signature_value,
    }
    data.update(shp_params)  # добавляем Shp_user_id

    base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
    return f"{base_url}?{urlencode(data)}"

# Проверка подписи при уведомлении от Robokassa (ResultURL)
def check_result_signature(params: dict) -> bool:
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    out_sum = params.get('OutSum')
    inv_id = params.get('InvId')
    signature = params.get('SignatureValue')
    if not all([out_sum, inv_id, signature]):
        return False
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    return my_signature == signature.upper()
