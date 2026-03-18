import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def get_weather(city: str = "Москва") -> str:
    """
    Получает текущую погоду для города через OpenWeatherMap API
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        logger.error("OPENWEATHER_API_KEY not set in environment variables")
        return ""

    # Используем http, а не https, чтобы избежать проблем с сертификатами
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
        "lang": "ru"
    }

    logger.info(f"Requesting weather for city: {city}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Weather API error for {city}: status {resp.status}, response: {error_text}")
                    return ""
                data = await resp.json()
                logger.info(f"Weather data received for {city}: {data}")

                # Извлекаем данные
                temp = data['main']['temp']
                feels_like = data['main']['feels_like']
                description = data['weather'][0]['description']
                wind = data['wind']['speed']

                weather_str = f"🌡 {temp:.1f}°C (ощущается как {feels_like:.1f}°C), {description}, ветер {wind:.1f} м/с"
                logger.info(f"Formatted weather string: {weather_str}")
                return weather_str
    except aiohttp.ClientConnectorError as e:
        logger.exception(f"Connection error for {city}: {e}")
        return ""
    except Exception as e:
        logger.exception(f"Unexpected error getting weather for {city}: {e}")
        return ""
