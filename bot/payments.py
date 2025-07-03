import uuid
import os
import requests

from database.db import SessionLocal
from database.models import User
from bot.config import PRICE_CHATTERBOX

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

def has_enough_balance(user_id: int, required_amount: float = PRICE_CHATTERBOX) -> bool:
    with SessionLocal() as session:
        user = session.query(User).filter_by(id=user_id).first()
        return user is not None and user.balance >= required_amount

def deduct_balance(user_id: int, amount: float = PRICE_CHATTERBOX) -> bool:
    with SessionLocal() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if user and user.balance >= amount:
            user.balance -= amount
            session.commit()
            return True
        return False
