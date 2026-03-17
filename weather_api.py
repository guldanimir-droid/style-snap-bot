import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def get_weather(city: str = "Moscow") -> str:
    """
    Получает текущую погоду для города через OpenWeatherMap API
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        logger.warning("OPENWEATHER_API_KEY not set")
        return ""
    
    url = f"http://ru.api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
        "lang": "ru"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Weather API error: {resp.status}")
                    return ""
                data = await resp.json()
                
                temp = data['main']['temp']
                feels_like = data['main']['feels_like']
                description = data['weather'][0]['description']
                wind = data['wind']['speed']
                
                return f"🌡 {temp:.1f}°C (ощущается как {feels_like:.1f}°C), {description}, ветер {wind:.1f} м/с"
    except Exception as e:
        logger.exception(f"Error getting weather: {e}")
        return ""
