import os
import logging
import asyncio

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

# --- FSM ---
class ImageGenState(StatesGroup):
    AWAITING_PROMPT = State()

# --- Обработчики ---
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "Привет! Отправь описание (prompt) на английском для генерации изображения с помощью модели `ideogram-v3-turbo`.\n\n"
        "Пример:\nThe text \"V3 Turbo\" in the center middle..."
    )
    await state.set_state(ImageGenState.AWAITING_PROMPT)

async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()

    if len(prompt) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.")
        return

    await message.answer("⏳ Генерация изображения...")

    try:
        replicate.api_token = REPLICATE_API_TOKEN

        # Создаем prediction асинхронно
        prediction = await replicate.predictions.async_create(
            model="ideogram-ai/ideogram-v3-turbo",
            input={
                "prompt": prompt,
                "aspect_ratio": "9:16"
            }
        )

        # Ожидаем завершения генерации
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)
            logger.debug(f"[handle_prompt] Статус: {prediction.status}")

        if prediction.status != "succeeded" or not prediction.output:
            raise RuntimeError("Не удалось получить изображение")

        # Обработка результата (один URL или список)
        image_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output

        await message.answer_photo(image_url, caption=f"✅ Изображение по запросу:\n{prompt}")
        logger.info(f"[handle_prompt] Сгенерировано изображение: {image_url}")

    except Exception as e:
        logger.exception("Ошибка генерации изображения")
        await message.answer("❌ Произошла ошибка при генерации изображения.")

    await state.clear()

# --- Основной запуск ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("Не заданы переменные окружения BOT_TOKEN или REPLICATE_API_TOKEN")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_prompt, StateFilter(ImageGenState.AWAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
