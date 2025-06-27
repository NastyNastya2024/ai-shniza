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
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("tg_bot")

# --- FSM ---
class ImageGenState(StatesGroup):
    AWAITING_PROMPT = State()

# --- Обработчики ---
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"[cmd_start] Пользователь {message.from_user.id} вызвал /start")
    await message.answer(
        "Привет! Отправь описание (промпт) на английском для генерации изображения.\n"
        "Минимум 15 символов.\n\nПример:\nA fantasy castle on a floating island at sunset"
    )
    await state.set_state(ImageGenState.AWAITING_PROMPT)

async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"[handle_prompt] Промпт от {user_id}: {prompt}")

    if len(prompt) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.")
        return

    await message.answer("⏳ Генерация изображения...")

    try:
        # Устанавливаем токен API для replicate
        replicate.api_token = REPLICATE_API_TOKEN

        # Асинхронное создание предсказания
        prediction = await replicate.predictions.async_create(
            model="google/imagen-4",
            input={
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "output_format": "png",
                "safety_filter_level": "block_medium_and_above",
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        )

        # Ожидание завершения предсказания
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)
            logger.debug(f"[handle_prompt] Ожидание... статус: {prediction.status}")

        if prediction.status == "failed":
            raise RuntimeError(f"Генерация не удалась. Статус: {prediction.status}")

        logger.debug(f"[handle_prompt] prediction.output: {prediction.output}")

        output = prediction.output

        if not output:
            raise ValueError("Отсутствует URL изображения")

        # Обработка формата output: список или строка
        if isinstance(output, list) and len(output) > 0:
            image_url = output[0]
        elif isinstance(output, str):
            image_url = output
        else:
            raise ValueError("Формат output неожиданный")

        logger.info(f"[handle_prompt] Успешно: {image_url}")
        await message.answer_photo(image_url, caption=f"✅ Ваше изображение:\n{prompt}")

    except Exception as e:
        logger.exception(f"[handle_prompt] Ошибка генерации: {e}")
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
    dp.message.register(handle_prompt, StateFilter(ImageGenState.AWAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
