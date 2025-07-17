import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

import replicate
from dotenv import load_dotenv

from keyboards import main_menu_kb, MAIN_MENU_BUTTON_TEXT

# --- Константы ---
REGENERATE_BUTTON_TEXT = "🔁 Новая генерация"

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Логирование ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("tg_bot")

# --- FSM ---
class IdeogramImageGenState(StatesGroup):
    SELECTING_ASPECT = State()
    SELECTING_STYLE = State()
    AWAITING_PROMPT = State()

# --- Клавиатура управления ---
def ideogram_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=REGENERATE_BUTTON_TEXT)],
        [KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)]
    ], resize_keyboard=True)

# --- Клавиатура выбора соотношения ---
def aspect_ratio_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="ideogram_aspect_1:1"),
            InlineKeyboardButton(text="9:16", callback_data="ideogram_aspect_2:3"),
            InlineKeyboardButton(text="16:9", callback_data="ideogram_aspect_16:9"),
        ]
    ])

# --- Клавиатура выбора стиля ---
def style_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Auto", callback_data="ideogram_style_auto"),
            InlineKeyboardButton(text="General", callback_data="ideogram_style_general"),
            InlineKeyboardButton(text="Anime", callback_data="ideogram_style_anime"),
        ],
        [
            InlineKeyboardButton(text="Realistic", callback_data="ideogram_style_realistic"),
            InlineKeyboardButton(text="Design", callback_data="ideogram_style_design"),
            InlineKeyboardButton(text="Render 3D", callback_data="ideogram_style_render3d"),
        ]
    ])

# --- Старт генерации ---
async def ideogram_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🖼 Ideogram V2 Turbo — генерация изображений по текстовому описанию на английском.\n\n"
        "📋 *Возможности:*\n"
        "- Генерация реалистичных и художественных изображений\n"
        "- Поддержка различных соотношений сторон\n"
        "- Высокое качество и детализация\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — только на английском языке\n"
        "- 💰 Стоимость: бесплатно (или укажи, если платно)",
        parse_mode="Markdown"
    )
    await state.set_state(IdeogramImageGenState.SELECTING_ASPECT)
    await message.answer("⬇️ Выбери соотношение сторон:", reply_markup=aspect_ratio_kb())

# --- Главное меню ---
async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Вы в главном меню", reply_markup=main_menu_kb())

# --- Обработка кнопок управления ---
async def handle_control_buttons(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == REGENERATE_BUTTON_TEXT:
        await ideogram_start(message, state)
    elif text == MAIN_MENU_BUTTON_TEXT:
        await go_main_menu(message, state)

# --- Обработка выбора соотношения ---
async def handle_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    aspect = callback.data.replace("ideogram_aspect_", "")
    await state.update_data(aspect_ratio=aspect)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Соотношение выбрано: {aspect}\n\nТеперь выбери стиль:",
        reply_markup=style_type_kb()
    )
    await state.set_state(IdeogramImageGenState.SELECTING_STYLE)
    await callback.answer()

# --- Обработка выбора стиля ---
async def handle_style_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    style = callback.data.replace("ideogram_style_", "")
    await state.update_data(style=style)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Стиль выбран: {style}\n\n✏️ Введите описание (prompt) на английском:",
        reply_markup=ideogram_menu_kb()
    )
    await state.set_state(IdeogramImageGenState.AWAITING_PROMPT)
    await callback.answer()

# --- Обработка prompt ---
async def handle_prompt_aspect_ideogram(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == REGENERATE_BUTTON_TEXT:
        await ideogram_start(message, state)
        return

    if text == MAIN_MENU_BUTTON_TEXT:
        await go_main_menu(message, state)
        return

    if len(text) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.", reply_markup=ideogram_menu_kb())
        return

    await message.answer("⏳ Генерация изображения...", reply_markup=ideogram_menu_kb())
    data = await state.get_data()
    aspect = data.get("aspect_ratio", "1:1")
    style = data.get("style", "auto")

    try:
        replicate.api_token = REPLICATE_API_TOKEN

        prediction = await replicate.predictions.async_create(
            model="ideogram-ai/ideogram-v2-turbo",
            input={
                "prompt": text,
                "aspect_ratio": aspect,
                "style": style
            }
        )

        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status != "succeeded" or not prediction.output:
            raise RuntimeError("Генерация не удалась")

        image_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output
        await message.answer_photo(image_url, caption=f"✅ Prompt: {text}", reply_markup=ideogram_menu_kb())

    except Exception as e:
        logger.exception("Ошибка генерации изображения")
        await message.answer("❌ Произошла ошибка при генерации.", reply_markup=ideogram_menu_kb())

    await state.clear()

# --- Запуск (только для отладки) ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("Не заданы переменные окружения BOT_TOKEN или REPLICATE_API_TOKEN")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(ideogram_start, Command("start"))
    dp.callback_query.register(handle_aspect_ideogram, F.data.startswith("ideogram_aspect_"), StateFilter(IdeogramImageGenState.SELECTING_ASPECT))
    dp.callback_query.register(handle_style_aspect_ideogram, F.data.startswith("ideogram_style_"), StateFilter(IdeogramImageGenState.SELECTING_STYLE))
    dp.message.register(handle_prompt_aspect_ideogram, StateFilter(IdeogramImageGenState.AWAITING_PROMPT))

    # Поддержка кнопок на всех этапах
    dp.message.register(handle_control_buttons, F.text.in_({REGENERATE_BUTTON_TEXT, MAIN_MENU_BUTTON_TEXT}))
    dp.message.register(handle_control_buttons, StateFilter(IdeogramImageGenState.SELECTING_ASPECT))
    dp.message.register(handle_control_buttons, StateFilter(IdeogramImageGenState.SELECTING_STYLE))
    dp.message.register(handle_control_buttons, StateFilter(IdeogramImageGenState.AWAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
