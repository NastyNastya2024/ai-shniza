import os
import logging
import asyncio
import random

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

import replicate
from dotenv import load_dotenv

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("tg_bot")

# --- Состояния FSM ---
class KlingState(StatesGroup):
    WAITING_IMAGE = State()
    WAITING_PROMPT = State()

# --- Команда /start ---
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("👋 Привет! Отправь изображение, которое хочешь анимировать.")
    await state.set_state(KlingState.WAITING_IMAGE)

# --- Обработка изображения ---
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Теперь отправь описание действия (prompt), например:\n`a woman takes her hands out her pockets and gestures to the words with both hands, she is excited, behind her it is raining`")
    await state.set_state(KlingState.WAITING_PROMPT)

# --- Обработка промпта и генерация видео ---
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    data = await state.get_data()
    image_url = data.get("image_url")

    if not image_url:
        await message.answer("❌ Изображение не найдено. Начни заново с /start.")
        return

    await message.answer("⏳ Генерирую видео... Это может занять пару минут.")

    try:
        os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN  # для replicate.run()
        output = replicate.run(
            "kwaivgi/kling-v2.1",
            input={
                "mode": "standard",
                "prompt": prompt,
                "duration": 5,
                "start_image": image_url,
                "negative_prompt": ""
            }
        )

        if output and isinstance(output, str) and output.startswith("http"):
            await message.answer_video(output, caption=f"✅ Готово!\n\n🔤 *Prompt:* {prompt}", parse_mode="Markdown")
        else:
            await message.answer("❌ Не удалось получить видео. Попробуй позже.")
            logger.error(f"[handle_prompt] Неверный ответ: {output}")

    except Exception as e:
        logger.exception("[handle_prompt] Ошибка генерации видео")
        await message.answer("❌ Произошла ошибка при генерации. Попробуйте позже.")

    await state.clear()

# --- Основной запуск ---
async def main():
    logger.info("Запуск Telegram-бота...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image, StateFilter(KlingState.WAITING_IMAGE))
    dp.message.register(handle_prompt, StateFilter(KlingState.WAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
