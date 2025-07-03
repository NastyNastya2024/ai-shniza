import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")  # Загружаем токен из переменной окружения BOT_TOKEN

PRICE_PER_GENERATION = int(os.getenv("PRICE_PER_GENERATION", "199"))
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "https://example.com/payment-link")
ALLOW_GENERATION_WHEN_ZERO = False  # если хочешь менять поведение при нуле
NO_GENERATION_MESSAGE = "Недостаточно средств на балансе. Пожалуйста, пополните баланс."


# Количество бесплатных генераций новому пользователю
FREE_GENERATIONS_ON_START = 1

# Разрешить ли генерацию при нуле (например, для отладки)
ALLOW_GENERATION_WHEN_ZERO = False

# Цены
PRICE_CHATTERBOX = 14.0
PRICE_IMAGE_GEN = 14.0 


