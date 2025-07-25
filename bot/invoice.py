from aiogram.types import LabeledPrice
from bot.config import PROVIDER_TOKEN
import json

def create_invoice(chat_id, amount=10000, description="Списание происходит только по факту генерации"):
    return {
        "chat_id": chat_id,
        "title": "Пополнение баланса",
        "description": description,
        "payload": "payment-payload",
        "provider_token": PROVIDER_TOKEN,
        "start_parameter": "payment-start",
        "currency": "RUB",
        "prices": [LabeledPrice(label="Пополнение", amount=amount)],
        "need_email": True,
        "provider_data": json.dumps({  # 👈 ОБЯЗАТЕЛЬНО сериализуем
            "receipt": {
                "customer": {
                    "full_name": "Komarova Anastasia Aleksandrovna",
                    "email": "anastkomarova@yandex.ru",
                    "phone": "79060959295",
                    "inn": "504231947047"
                },
                "items": [
                    {
                        "description": "Пополнение баланса",
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount / 100:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "commodity"
                    }
                ],
                "tax_system_code": 1
            }
        })
    }
