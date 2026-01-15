import requests
from django.conf import settings

PRODUCT_SERVICE_URL = settings.PRODUCT_SERVICE_URL

def fetch_product(product_id):
    response = requests.get(
        f"{PRODUCT_SERVICE_URL}/api/products/{product_id}/"
    )
    response.raise_for_status()
    return response.json()