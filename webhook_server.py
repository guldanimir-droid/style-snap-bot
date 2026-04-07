import os
import hashlib
from aiohttp import web
from database import add_paid_requests   # мы сейчас создадим эту функцию
import logging

logger = logging.getLogger(__name__)

async def result_handler(request):
    """Обработчик уведомлений от Robokassa (ResultURL)"""
    data = await request.post()
    logger.info(f"Получено уведомление: {data}")

    out_sum = data.get('OutSum')
    inv_id = data.get('InvId')
    signature = data.get('SignatureValue')
    shp_user_id = data.get('Shp_user_id')

    if not all([out_sum, inv_id, signature, shp_user_id]):
        logger.warning("Не хватает параметров")
        return web.Response(text='Missing params', status=400)

    # Проверяем подпись (используем PASSWORD2)
    password2 = os.getenv('ROBOKASSA_PASSWORD2')
    my_signature = hashlib.md5(f"{out_sum}:{inv_id}:{password2}".encode()).hexdigest().upper()
    if my_signature != signature.upper():
        logger.warning(f"Неверная подпись: {signature} vs {my_signature}")
        return web.Response(text='Bad sign', status=400)

    # Определяем, сколько анализов куплено по сумме
    amount = float(out_sum)
    if amount == 25.0:
        paid_count = 1
    elif amount == 50.0:
        paid_count = 3
    elif amount == 75.0:
        paid_count = 5
    elif amount == 500.0:
        # Для подписки можно потом добавить логику, пока просто 0
        paid_count = 0
    else:
        paid_count = 0

    if paid_count > 0:
        # Начисляем анализы пользователю
        add_paid_requests(shp_user_id, paid_count)
        logger.info(f"Пользователю {shp_user_id} начислено {paid_count} анализов")
    else:
        logger.info(f"Неизвестная сумма {amount}, начисление не выполнено")

    # Robokassa требует ответ "OK" (именно большими буквами)
    return web.Response(text='OK')

def start_webhook_server():
    """Запускает aiohttp сервер на порту 8000"""
    app = web.Application()
    app.router.add_post('/robokassa/result', result_handler)
    # Запуск сервера (будет работать в отдельной задаче)
    from aiohttp.web import run_app
    run_app(app, port=8000)
