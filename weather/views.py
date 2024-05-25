import logging
from datetime import datetime, timedelta

import requests
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import District

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather_forecast(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m",
        "timezone": "Asia/Dhaka",
        "start": datetime.utcnow().isoformat(),
        "end": (datetime.utcnow() + timedelta(days=7)).isoformat(),
    }
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
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


@api_view(["GET"])
def get_coolest_districts(request):
    try:
        districts = District.objects.all()
        district_temps = []

        for district in districts:
            try:
                weather_data = fetch_weather_forecast(district.lat, district.lon)
                daily_temps = get_daily_2PM_temps(weather_data)
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
            except Exception as ex:
                logger.error(f"Failed to process district {district.name}: {ex}")

        district_temps.sort(key=lambda x: x["average_temp"])
        coolest_districts = district_temps[:10]

        for district in coolest_districts:
            district.pop("average_temp")

        return Response({"data": coolest_districts}, status=status.HTTP_200_OK)
    except Exception as ex:
        logger.error(f"Unexpected error: {ex}")
        return Response(
            {"error": "An unexpected error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def compare_temperatures(request):
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
        origin = District.objects.get(name=friend_location)
        destination = District.objects.get(name=destination_name)
    except ObjectDoesNotExist:
        return Response(
            {"error": "Invalid origin or destination"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        origin_weather = fetch_weather_forecast(origin.lat, origin.lon)
        destination_weather = fetch_weather_forecast(destination.lat, destination.lon)
    except Exception as ex:
        logger.error(f"Failed to fetch weather data: {ex}")
        return Response(
            {"error": "Failed to fetch weather data"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    origin_temp = next(
        (
            temp
            for i, temp in enumerate(origin_weather["hourly"]["temperature_2m"])
            if travel_date.strftime("%Y-%m-%d") in origin_weather["hourly"]["time"][i]
            and "14:00" in origin_weather["hourly"]["time"][i]
        ),
        None,
    )
    destination_temp = next(
        (
            temp
            for i, temp in enumerate(destination_weather["hourly"]["temperature_2m"])
            if travel_date.strftime("%Y-%m-%d")
            in destination_weather["hourly"]["time"][i]
            and "14:00" in destination_weather["hourly"]["time"][i]
        ),
        None,
    )

    if origin_temp is None or destination_temp is None:
        return Response(
            {"error": "Temperature data not available for the given date"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    decision = (
        "Yes, it is cooler!. You can go"
        if destination_temp < origin_temp
        else "No, it is not cooler. You should no travel"
    )
    return Response(
        {
            "friend's_location_temperature": f"{origin_temp:.2f} °C",
            "destination_temperature": f"{destination_temp:.2f} °C",
            "decision": decision,
        },
        status=status.HTTP_200_OK,
    )
