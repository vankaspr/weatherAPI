import os
import httpx
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from  fastapi_cache.decorator import  cache
from aioredis import Redis
from functools import lru_cache


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI()


redis_cashe = Redis(host="localhost", port=6379, db=0)
FastAPICache.init(RedisBackend(redis_cashe), prefix="weather_cache")


@lru_cache
def get_api_keys():
    return {
        "openweathermap": os.getenv("OPENWEATHERMAP_API_KEY"),
        "visualcrossing": os.getenv("VISUALCROSSING_API_KEY")
    }


class WeatherApi:
    """Базовый класс для API погоды"""
    
    
    BASE_URL = ""
    
    
    def __init__(self, api_key: str):
        self.api_key = api_key

    
    async def fetch(self, city: str) -> dict:
        """Асинхронный запрос к API погоды"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.build_url(city), params=self.get_params(city))
                response.raise_for_status()
                return self.parse_response(response.json())
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP {e.response.status_code} -> query {self.BASE_URL}: {e}" )
                return {"error": f"API error: {e.response.status_code}"}
            except httpx.RequestError as e:
                logger.error(f"Query error {self.BASE_URL}: {e}")
                return {"error": "Request error"}
            except Exception as e:
                logger.error(f"Unknown error: {e}")
                return {"error": "Unknown error"}
            
    
    
    def build_url(self,  city: str) -> str:
        """Формирование URL (переопределяется в наседниках)"""
        raise NotImplementedError
    
    
    def get_params(self, city: str) -> str:
        """Формирование параметров запроса (переопределяется в наследниках)"""
        raise NotImplementedError
    
    
    def parse_response(self, response: dict) -> dict:
        """Обработка данных ответа (переопределяется в наследниках)"""
        raise NotImplementedError


class VisualCrossingAPI(WeatherApi):
    """Класс для работы с VisualCrossing API"""
    
    
    BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
    
    
    def build_url(self, city) -> str:
        return f"{self.BASE_URL/{city}}"
    
    
    def get_params(self, city) -> dict:
        return {
            "key" : self.api_key,
            "unitGroup" :"metric",
            "include" : "current",
        }
        
    def parse_response(self, response):
        return {
            "source": "VisualCrossing",
            "temperature": response["currentConditions"]["temp"],
            "description": response["currentConditions"]["conditions"],
            "humidity": response["currentConditions"]["humidity"],
            "feels_like": response["currentConditions"]["feelslike"]
        }


class OpenWeatherAPI(WeatherApi):
    """Класс для работы с OpenWeatherMap API """
    
    BASE_URL = f"http://api.openweathermap.org/data/2.5/weather"
    
    
    def build_url(self, city) -> str:
        return self.BASE_URL
    
    
    def get_params(self, city) -> dict:
        return {
            "q": city,
            "appid": self.api_key,
            "units": "metric", 
        }
        
        
    def parse_response(self, response):
        return {
            "source": "OpenWeatherMap",
            "temperature": response["main"]["temp"],
            "description": response["weather"][0]["description"],
            "humidity": response["main"]["humidity"],
            "feels_like": response["main"]["feels_like"]
        }


async def get_weather(city) -> dict:
    """Опрашиваем несколько API и берем первое доступное"""
    
    api_keys = get_api_keys()
    sources =[
        VisualCrossingAPI(api_keys["visualcrossing"]),
        OpenWeatherAPI(api_keys["openweathermap"]),
    ]
    
    for source in sources:
        data =  await source.fetch(city)
        if "error" not in data:
            return data

    return {"error": "unable fetch weather data from any source."}


@app.get("/")
def hello():
    return {"message": "welcome to Weather API ૮ ˶ᵔ ᵕ ᵔ˶ ა"}


@app.get("/weather/{city}")
@cache(expire=300)
async def weather(city: str):
    """Эндпоинт для получения погоды"""
    return await get_weather(city)


# uvicorn main:app --reload