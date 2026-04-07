import hashlib
import os
import time
import json
from urllib.parse import urlencode

async def generate_payment_link(user_id: str, amount: float, description: str) -> str:
    login = os.getenv('ROBOKASSA_LOGIN')
    password1 = os.getenv('ROBOKASSA_PASSWORD1')
    is_test = int(os.getenv('ROBOKASSA_TEST', 1)) == 1

    invoice_id = int(time.time() * 1000) % 1000000000

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

    data = {
        'MerchantLogin': login,
        'OutSum': f"{amount:.2f}",
        'InvId': invoice_id,
        'Description': description,
        'Receipt': receipt_json,
        'IsTest': 1 if is_test else 0,
    }

    signature_str = f"{login}:{amount:.2f}:{invoice_id}:{receipt_json}:{password1}"
    data['SignatureValue'] = hashlib.md5(signature_str.encode()).hexdigest().upper()

    base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
    return f"{base_url}?{urlencode(data)}"

def check_result_signature(params: dict) -> bool:
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    out_sum = params.get('OutSum')
    inv_id = params.get('InvId')
    signature = params.get('SignatureValue')
    if not all([out_sum, inv_id, signature]):
        return False
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    return my_signature == signature.upper()
