import time
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Update

class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, time_limit: int = 10):
        super().__init__()
        self.user_requests = defaultdict(list)
        self.time_limit = time_limit

    async def __call__(self, handler, event: Update, data: dict):
        if isinstance(event, Update) and event.message:
            user_id = event.message.from_user.id
            current_time = time.time()

            self.user_requests[user_id] = [
                req_time for req_time in self.user_requests[user_id]
                if current_time - req_time < self.time_limit
            ]

            if len(self.user_requests[user_id]) >= 1:
                await event.message.answer(
                    f"⏳ Пожалуйста, не спешите. Подождите {self.time_limit} секунд перед следующим запросом."
                )
                return
            self.user_requests[user_id].append(current_time)

        return await handler(event, data)
