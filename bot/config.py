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


BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY")

# Этот токен используется Telegram при выставлении счета через бот @YooKassaTestShopBot
# Обрати внимание: это НЕ YOOKASSA_API_KEY, а именно Telegram-совместимый токен
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "424924419:TEST:your_yookassa_telegram_token")
