from cachetools import TTLCache

# Храним результаты анализа для каждого пользователя не более 1 часа
last_results_cache = TTLCache(maxsize=10000, ttl=3600)
