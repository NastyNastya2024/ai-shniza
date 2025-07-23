from aiogram.types import LabeledPrice
from bot.config import PROVIDER_TOKEN

def create_invoice(chat_id, amount=10000, description="Списание происходит только по факту генерации"):
    return {
        "chat_id": chat_id,
        "title": "Пополнение баланса",
        "description": description,
        "payload": "payment-payload",
        "provider_token": PROVIDER_TOKEN,
        "start_parameter": "payment-start",
        "currency": "RUB",
        "prices": [LabeledPrice(label="Пополнение", amount=amount)],  # в копейках
        "need_email": True
    }
