import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# --- FSM ---
class ImageGenState(StatesGroup):
    SELECTING_ASPECT = State()
    SELECTING_STYLE = State()
    AWAITING_PROMPT = State()

# --- Клавиатуры ---
def aspect_ratio_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="ideogram_aspect_1:1"),
            InlineKeyboardButton(text="9:16", callback_data="ideogram_aspect_2:3"),
            InlineKeyboardButton(text="16:9", callback_data="ideogram_aspect_16:9"),
        ]
    ])

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

# --- /start ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🖼 Ideogram V2 Turbo — генерация изображений по текстовому описанию на английском.\n\n"
        "📋 *Возможности:*\n"
        "- Генерация реалистичных и художественных изображений\n"
        "- Поддержка различных соотношений сторон\n"
        "- Высокое качество и детализация\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — только на английском языке\n"
        "- 💰 Стоимость: бесплатно (или укажи, если платно)\n\n"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

    # Сразу предлагаем выбрать соотношение сторон
    await state.set_state(ImageGenState.SELECTING_ASPECT)
    await message.answer(
        "Выбери соотношение сторон изображения:",
        reply_markup=aspect_ratio_kb()
    )

# --- Обработка выбора соотношения сторон ---
async def handle_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    aspect = callback.data.replace("ideogram_aspect_", "")
    await state.update_data(aspect_ratio=aspect)
    await callback.message.edit_text(
        f"✅ Соотношение выбрано: {aspect}\n\nТеперь выбери стиль:",
        reply_markup=style_type_kb()
    )
    await state.set_state(ImageGenState.SELECTING_STYLE)

# --- Обработка выбора стиля ---
async def handle_style_aspect_ideogram(callback: CallbackQuery, state: FSMContext):
    style = callback.data.replace("ideogram_style_", "")
    await state.update_data(style=style)
    await callback.message.edit_text(
        f"✅ Стиль установлен: {style}\n\n✏️ Теперь отправь описание (prompt) на английском."
    )
    await state.set_state(ImageGenState.AWAITING_PROMPT)

# --- Обработка prompt ---
async def handle_prompt_aspect_ideogram(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.")
        return

    user_data = await state.get_data()
    aspect_ratio = user_data.get("aspect_ratio", "1:1")
    style = user_data.get("style", "auto")

    await message.answer("⏳ Генерация изображения...")

    try:
        replicate.api_token = REPLICATE_API_TOKEN

        prediction = await replicate.predictions.async_create(
            model="ideogram-ai/ideogram-v2-turbo",
            input={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "style": style
            }
        )

        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status != "succeeded" or not prediction.output:
            raise RuntimeError("Не удалось получить изображение")

        image_url = prediction.output[0] if isinstance(prediction.output, list) else prediction.output
        await message.answer_photo(image_url, caption=f"✅ Prompt: {prompt}")

    except Exception as e:
        logger.exception("Ошибка генерации изображения")
        await message.answer("❌ Произошла ошибка при генерации.")

    await state.clear()

# --- Запуск ---
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("Не заданы переменные окружения BOT_TOKEN или REPLICATE_API_TOKEN")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(handle_aspect_ideogram, F.data.startswith("ideogram_aspect_"), StateFilter(ImageGenState.SELECTING_ASPECT))
    dp.callback_query.register(handle_style_aspect_ideogram, F.data.startswith("ideogram_style_"), StateFilter(ImageGenState.SELECTING_STYLE))
    dp.message.register(handle_prompt_aspect_ideogram, StateFilter(ImageGenState.AWAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
