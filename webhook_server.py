import os
import hashlib
from aiohttp import web
import logging

logger = logging.getLogger(__name__)

async def result_handler(request):
    """Принимает уведомление от Robokassa после оплаты"""
    data = await request.post()
    logger.info(f"Уведомление от Robokassa: {dict(data)}")

    out_sum = data.get('OutSum')
    inv_id = data.get('InvId')
    signature = data.get('SignatureValue')
    shp_user_id = data.get('Shp_user_id')

    if not all([out_sum, inv_id, signature, shp_user_id]):
        logger.warning("Не хватает параметров")
        return web.Response(text='Missing params', status=400)

    # Проверяем подпись
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    if my_signature != signature.upper():
        logger.warning(f"Неверная подпись: {signature} vs {my_signature}")
        return web.Response(text='Bad sign', status=400)

    # Определяем количество купленных анализов по сумме
    amount = float(out_sum)
    if amount == 25.0:
        paid_count = 1
    elif amount == 50.0:
        paid_count = 3
    elif amount == 75.0:
        paid_count = 5
    elif amount == 500.0:
        paid_count = 0  # подписка – обработайте позже
    else:
        paid_count = 0

    if paid_count > 0:
        from database import add_paid_requests
        add_paid_requests(shp_user_id, paid_count)
        logger.info(f"Пользователю {shp_user_id} начислено {paid_count} анализов")
    else:
        logger.info(f"Сумма {amount} не соответствует пакету анализов, начисление не выполнено")

    # Обязательный ответ "OK"
    return web.Response(text='OK')
