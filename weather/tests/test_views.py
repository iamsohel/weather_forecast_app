import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from weather.models import District

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest_asyncio.fixture
async def setup_data():
    await sync_to_async(District.objects.create)(
        name="Noakhali", lat=23.8103, lon=90.4125
    )
    await sync_to_async(District.objects.create)(
        name="Cox bazar", lat=22.3569, lon=91.7832
    )


@pytest.mark.asyncio
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
async def test_get_coolest_districts(api_client, setup_data):
    url = reverse("coolest_districts")
    response = await sync_to_async(api_client.get)(url)
    assert response.status_code == 200
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_compare_temperatures(api_client, setup_data):
    url = reverse("compare_temperatures")
    response = await sync_to_async(api_client.get)(
        url,
        {
            "friend_location": "Noakhali",
            "destination": "Cox bazar",
            "date": "2024-05-27",
        },
    )
    print(response.json())
    assert response.status_code == 200
    assert "friend's_location_temperature" in response.json()
    assert "destination_temperature" in response.json()
    assert "decision" in response.json()


@pytest.mark.asyncio
async def test_compare_temperatures_missing_params(api_client):
    url = reverse("compare_temperatures")
    response = await sync_to_async(api_client.get)(url)
    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_compare_temperatures_invalid_date(api_client, setup_data):
    url = reverse("compare_temperatures")
    response = await sync_to_async(api_client.get)(
        url,
        {
            "friend_location": "Noakhali",
            "destination": "Cox bazar",
            "date": "invalid-date",
        },
    )
    assert response.status_code == 400
    assert "error" in response.json()
