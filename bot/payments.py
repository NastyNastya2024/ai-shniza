import uuid
import os
import requests

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY")

def create_payment(amount: float, return_url: str, description: str = "Оплата"):
    payment_id = str(uuid.uuid4())

    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": payment_id,
    }

    auth = (YOOKASSA_SHOP_ID, YOOKASSA_API_KEY)

    data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "capture": True,
        "description": description
    }

    response = requests.post(
        'https://api.yookassa.ru/v3/payments',
        headers=headers,
        auth=auth,
        json=data
    )

    result = response.json()
    return result
