# main.py
import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.filters import Command

from database import init_db
from balance import balance_router
from generation import generation_router


# Инициализация хранилища состояний
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Главное меню
def start_menu_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎨 Генерация")],
        [KeyboardButton(text="📊 Баланс")]
    ], resize_keyboard=True)


# Команда /start
async def cmd_start(message: Message):
    from balance import get_or_create_user
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer("✅ Старт принят!")
    await message.answer(
        f"Привет, {message.from_user.first_name}!\nВыберите действие:",
        reply_markup=start_menu_keyboard()
    )


# Обработчик "Главное меню"
async def main_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=start_menu_keyboard())


# Регистрация всех хендлеров
def register_handlers(dp: Dispatcher):
    dp.include_router(balance_router)
    dp.include_router(generation_router)
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(main_menu, lambda m: m.text == "Главное меню")


# Основная точка входа
async def main():
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не найден в .env")
        return

    init_db()
    print("✅ База данных готова")

    bot = Bot(token=BOT_TOKEN)
    register_handlers(dp)

    # Удаление webhook (если вдруг был установлен)
    await bot.delete_webhook(drop_pending_updates=True)

    # Запуск long polling
    print("🤖 Бот запущен через polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
