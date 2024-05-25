import json

import requests
from django.core.management.base import BaseCommand

from weather.models import District


class Command(BaseCommand):
    help = "Fetch and save district data"

    def handle(self, *args, **kwargs):
        url = "https://raw.githubusercontent.com/strativ-dev/technical-screening-test/main/bd-districts.json"
        response = requests.get(url)
        data = response.json()
        for district in data["districts"]:
            print(district)
            District.objects.update_or_create(
                name=district["name"],
                bn_name=district["bn_name"],
                defaults={"lat": district["lat"], "lon": district["long"]},
            )

        self.stdout.write(
            self.style.SUCCESS("Successfully fetched and saved districts")
        )
