import hashlib
import os
import aiohttp
from urllib.parse import urlencode

async def generate_payment_link(user_id: str, amount: float, description: str) -> str:
    login = os.getenv('ROBOKASSA_LOGIN')
    password1 = os.getenv('ROBOKASSA_PASSWORD1')
    is_test = int(os.getenv('ROBOKASSA_TEST', 1)) == 1

    # Для простоты используем user_id + timestamp как номер счёта
    import time
    invoice_id = int(time.time()) % 1000000  # небольшое число

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

async def check_payment_status(invoice_id: int):
    login = os.getenv('ROBOKASSA_LOGIN')
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    is_test = int(os.getenv('ROBOKASSA_TEST', 1)) == 1

    url = "https://test.robokassa.ru/Webservice/Service.asmx/OpState"
    if not is_test:
        url = "https://auth.robokassa.ru/Webservice/Service.asmx/OpState"

    params = {
        'MerchantLogin': login,
        'InvId': invoice_id,
        'Signature': hashlib.md5(f"{invoice_id}:{password2}".encode()).hexdigest().upper()
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
            # Простой парсинг XML (можно через xml.etree.ElementTree, но для простоты так)
            if '<Result>0</Result>' in text:
                return {'status': 'failure'}
            elif '<Result>1</Result>' in text:
                import re
                match = re.search(r'<Sum>([\d.]+)</Sum>', text)
                amount = float(match.group(1)) if match else 0
                return {'status': 'success', 'amount': amount}
            return None
