import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from asgiref.sync import async_to_sync, sync_to_async
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import District

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"


async def fetch_weather_forecast(session, lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m",
        "timezone": "Asia/Dhaka",
        "start": datetime.utcnow().isoformat(),
        "end": (datetime.utcnow() + timedelta(days=7)).isoformat(),
    }
    try:
        async with session.get(API_URL, params=params) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Failed to fetch weather data: {e}")
        raise


def get_daily_2PM_temps(weather_data):
    hourly_temps = weather_data["hourly"]["temperature_2m"]
    timestamps = weather_data["hourly"]["time"]

    daily_temps = {}

    for i, timestamp in enumerate(timestamps):
        date_time = datetime.fromisoformat(timestamp)
        if date_time.hour == 14:
            date_str = date_time.strftime("%Y-%m-%d")
            daily_temps[date_str] = hourly_temps[i]

    next_7_days = [datetime.utcnow().date() + timedelta(days=i) for i in range(7)]
    daily_2pm_temps = {
        day.strftime("%a").lower(): daily_temps.get(day.strftime("%Y-%m-%d"))
        for day in next_7_days
    }
    return daily_2pm_temps


def calculate_average_temp(daily_temps):
    valid_temps = [temp for temp in daily_temps.values() if temp is not None]
    return sum(valid_temps) / len(valid_temps) if valid_temps else None


async def fetch_all_districts_weather_data(districts):
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_weather_forecast(session, district.lat, district.lon)
            for district in districts
        ]
        return await asyncio.gather(*tasks)


@sync_to_async
def get_districts():
    return list(District.objects.all())


async def get_coolest_districts_async():
    try:
        districts = await get_districts()

        cached_data = cache.get("coolest_districts")
        if cached_data:
            return {"data": cached_data}

        weather_data = await fetch_all_districts_weather_data(districts)

        district_temps = []
        for district, data in zip(districts, weather_data):
            daily_temps = get_daily_2PM_temps(data)
            avg_temp = calculate_average_temp(daily_temps)
            if avg_temp is not None:
                district_data = {"district": district.name}
                district_data.update(
                    {
                        day: f"{temp:.2f} °C"
                        for day, temp in daily_temps.items()
                        if temp is not None
                    }
                )
                district_data["average_temp"] = avg_temp
                district_temps.append(district_data)

        district_temps.sort(key=lambda x: x["average_temp"])
        coolest_districts = district_temps[:10]

        for district in coolest_districts:
            district.pop("average_temp")

        cache.set("coolest_districts", coolest_districts, timeout=60 * 5)

        return {"data": coolest_districts}
    except Exception as ex:
        logger.error(f"Unexpected error: {ex}")
        raise ex


@api_view(["GET"])
def get_coolest_districts(request):
    try:
        response_data = async_to_sync(get_coolest_districts_async)()
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as ex:
        return Response(
            {"error": "An unexpected error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_temperature_at_2pm_of_a_day(weather_data, travel_date):
    try:
        hourly_temps = weather_data["hourly"]["temperature_2m"]
        timestamps = weather_data["hourly"]["time"]
        for i, timestamp in enumerate(timestamps):
            if travel_date.strftime("%Y-%m-%d") in timestamp and "14:00" in timestamp:
                return hourly_temps[i]
    except KeyError as e:
        logger.error(f"Missing expected key in weather data: {e}")
    return None


async def compare_temperatures_async(request):
    friend_location = request.GET.get("friend_location")
    destination_name = request.GET.get("destination")
    date_str = request.GET.get("date")

    if not friend_location or not destination_name or not date_str:
        return Response(
            {"error": "Missing required parameters"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        travel_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return Response(
            {"error": "Invalid date format. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        origin = await sync_to_async(District.objects.get)(name=friend_location)
        destination = await sync_to_async(District.objects.get)(name=destination_name)
    except ObjectDoesNotExist:
        return Response(
            {"error": "Invalid origin or destination"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        async with aiohttp.ClientSession() as session:
            origin_weather, destination_weather = await asyncio.gather(
                fetch_weather_forecast(session, origin.lat, origin.lon),
                fetch_weather_forecast(session, destination.lat, destination.lon),
            )
    except Exception as ex:
        logger.error(f"Failed to fetch weather data: {ex}")
        return Response(
            {"error": "Failed to fetch weather data"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    origin_temp = get_temperature_at_2pm_of_a_day(origin_weather, travel_date)
    destination_temp = get_temperature_at_2pm_of_a_day(destination_weather, travel_date)

    if origin_temp is None or destination_temp is None:
        return Response(
            {"error": "Temperature data not available for the given date"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    decision = (
        "Yes, it is cooler!. You can go"
        if destination_temp < origin_temp
        else "No, it is not cooler. You should not travel"
    )
    return Response(
        {
            "friend's_location_temperature": f"{origin_temp:.2f} °C",
            "destination_temperature": f"{destination_temp:.2f} °C",
            "decision": decision,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def compare_temperatures(request):
    return async_to_sync(compare_temperatures_async)(request)
