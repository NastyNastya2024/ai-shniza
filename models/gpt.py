import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

import replicate

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Состояния FSM ---
class PromptTranslationState(StatesGroup):
    WAITING_RU_PROMPT = State()

# --- Команда /start ---
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(PromptTranslationState.WAITING_RU_PROMPT)
    await message.answer("✏️ Введите текст на русском для перевода на английский:")

# --- Обработка ввода и перевод через Replicate ---
async def handle_russian_prompt(message: Message, state: FSMContext):
    ru_prompt = message.text.strip()
    await message.answer("⏳ Перевожу...")

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        output = client.run(
            "openai/gpt-4.1-nano",
            input={
                "prompt": f"Переведи следующий текст на английский: {ru_prompt}",
                "top_p": 1,
                "temperature": 1,
                "system_prompt": "You are a helpful assistant.",
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "max_completion_tokens": 4096
            }
        )

        # Объединяем список токенов в строку
        translated_prompt = "".join(output).strip()

        await message.answer(
            f"✅ Перевод",
            parse_mode="Markdown"
        )
        await message.answer(
            f"`{translated_prompt}`",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("Ошибка при обращении к Replicate API")
        await message.answer("❌ Произошла ошибка при переводе. Попробуйте позже.")

    await state.clear()

# --- Запуск бота ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_russian_prompt, StateFilter(PromptTranslationState.WAITING_RU_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())