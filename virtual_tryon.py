import replicate
import logging
import asyncio

logger = logging.getLogger(__name__)

class VirtualTryOn:
    def __init__(self):
        self.model = "yisol/IDM-VTON:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f"
    
    async def try_on(self, person_image_url: str, clothing_image_url: str) -> str:
        """
        Выполняет виртуальную примерку одежды на фото человека.
        Возвращает URL результата.
        """
        try:
            output = replicate.run(
                self.model,
                input={
                    "model_type": "auto",
                    "category": "upper_body",
                    "person_image": person_image_url,
                    "cloth_image": clothing_image_url,
                    "background": "white",
                    "seed": 42,
                    "steps": 20
                }
            )
            # Результат может быть списком или строкой
            if isinstance(output, list) and len(output) > 0:
                return output[0]
            return output
        except Exception as e:
            logger.exception("Ошибка при вызове Replicate")
            raise e
