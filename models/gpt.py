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

from keyboards import main_menu_kb, MAIN_MENU_BUTTON_TEXT

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
    await message.answer(
        "✏️ Введите текст на русском для перевода на английский:",
    )

# --- Главное меню ---
async def go_main_menu(message: Message, state: FSMContext):
    logging.info(f"[MainMenu] Нажата кнопка: {message.text}")
    await state.clear()
    await message.answer("Вы в главном меню", reply_markup=main_menu_kb())

# --- Обработка ввода и перевод через Replicate ---
async def handle_russian_prompt(message: Message, state: FSMContext):
    user_input = message.text.strip()

    if user_input == MAIN_MENU_BUTTON_TEXT:
        await go_main_menu(message, state)
        return
    

    await message.answer("⏳ Перевожу...")

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        output = client.run(
            "openai/gpt-4.1-nano",
            input={
                "prompt": f"Переведи следующий текст на английский: {user_input}",
                "top_p": 1,
                "temperature": 1,
                "system_prompt": "You are a helpful assistant.",
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "max_completion_tokens": 4096
            }
        )

        translated_prompt = "".join(output).strip()
        await message.answer("✅ Перевод:")
        await message.answer(translated_prompt)

    except Exception as e:
        logger.exception("Ошибка при обращении к Replicate API")
        await message.answer("❌ Произошла ошибка при переводе. Попробуйте позже.")
