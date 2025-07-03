import os
import asyncio
import logging
import replicate
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Инициализация Replicate API
replicate.api_token = REPLICATE_API_TOKEN

# FSM состояние для ожидания текста для генерации видео
class VideoGenState(StatesGroup):
    waiting_for_prompt = State()

# Обработчик команды /start — сразу запрашиваем промпт
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        " Модель Veo3 генерирует видео с звуком по описанию.\n"
        "💡 Описание (prompt) — на английском.\n"
        "🛠️ Разрешение видео 16:9 .\n"
        "🛠️ Звук соответствует описанию.\n"
        "💲 Себестоимость: 6$ (комиссия отсутствует).\n"
        "Отправьте описание сцены."
    )
    await state.set_state(VideoGenState.waiting_for_prompt)

# Обработка текста с описанием сцены
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое, минимум 15 символов. Попробуйте еще раз:")
        return

    await message.answer("🎬 Генерируем видео, это может занять некоторое время...")

    try:
        output = replicate.run(
            "google/veo-3",
            input={
                "prompt": prompt,
                "enhance_prompt": True,
                "aspect_ratio": "16:9"  # дефолтное разрешение 16:9
            }
        )
        # Получаем URL видео из объекта output
        video_url = output.url if hasattr(output, "url") else output

        logger.info(f"Видео сгенерировано: {video_url}")
        await message.answer_video(video_url, caption="✅ Видео готово!")
    except Exception as e:
        logger.exception("Ошибка при генерации видео:")
        await message.answer("⚠️ Произошла ошибка при генерации видео.")

    await state.clear()

# Основная функция запуска бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_prompt, StateFilter(VideoGenState.waiting_for_prompt))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
