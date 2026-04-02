import replicate
import logging
import asyncio

logger = logging.getLogger(__name__)

# Пожалуйста, обратите внимание: Эта модель лицензирована как CC BY-NC-SA 4.0.
# Коммерческое использование, включая использование в боте с платной подпиской,
# может быть ограничено. Убедитесь, что вы соблюдаете условия лицензии.
MODEL_VERSION = "cuuupid/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f"

class VirtualTryOn:
    def __init__(self):
        pass

    async def try_on(self, person_image_url: str, clothing_image_url: str) -> str:
        try:
            # Асинхронный вызов модели на Replicate
            output = await replicate.async_run(
                MODEL_VERSION,
                input={
                    "human_img": person_image_url,
                    "garm_img": clothing_image_url,
                    "category": "upper_body", # Категория одежды
                    "crop": False, # Обрезать ли изображение человека до формата 3:4
                    "force_dc": False, # Использовать ли версию для платьев
                    "mask_only": False, # Генерировать только маску
                    "steps": 30, # Количество шагов диффузии
                    "seed": 42, # Зерно для воспроизводимости
                }
            )
            # Результат от Replicate может быть строкой (URL) или списком URL'ов
            if isinstance(output, list):
                return output[0] if output else None
            return output
        except Exception as e:
            logger.error(f"Ошибка при вызове Replicate: {e}")
            raise e
