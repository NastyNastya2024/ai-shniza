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

from keyboards import main_menu_kb, MAIN_MENU_BUTTON_TEXT

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

# --- FSM состояния ---
class ImageGenState(StatesGroup):
    AWAITING_ASPECT = State()
    AWAITING_PROMPT = State()

# --- Клавиатура выбора соотношения ---
def aspect_ratio_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="aspect_1:1"),
            InlineKeyboardButton(text="9:16", callback_data="aspect_9:16"),
            InlineKeyboardButton(text="16:9", callback_data="aspect_16:9"),
        ]
    ])

# --- Клавиатура повтор/меню ---
def imagegen_menu_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)]
    ], resize_keyboard=True)

# --- /start ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    logger.info(f"[cmd_start] Пользователь {message.from_user.id} вызвал /start")

    welcome_text = (
        "🖼 Google Imagen 4 — генерация изображений по текстовому описанию на английском языке.\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — только на английском языке\n"
        "- Минимум 15 символов\n"
        "- 💰 Стоимость: бесплатно\n\n"
        "⬇️ Выберите соотношение сторон:"
    )

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=aspect_ratio_kb())
    await state.set_state(ImageGenState.AWAITING_ASPECT)

# --- Главное меню ---
async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню", reply_markup=main_menu_kb())

# --- Обработка выбора соотношения сторон ---
async def aspect_imagegen4(callback: CallbackQuery, state: FSMContext):
    aspect_value = callback.data.split("_")[1]
    await state.update_data(aspect_ratio=aspect_value)
    logger.info(f"[aspect_imagegen4] Пользователь {callback.from_user.id} выбрал аспект {aspect_value}")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте описание (промпт) на английском языке (минимум 15 символов):", reply_markup=imagegen_menu_kb())
    await state.set_state(ImageGenState.AWAITING_PROMPT)
    await callback.answer()

# --- Обработка промпта ---
async def handle_prompt(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "🔁 Повторить генерацию":
        await cmd_start(message, state)
        return

    if text == MAIN_MENU_BUTTON_TEXT:
        await go_main_menu(message, state)
        return

    user_id = message.from_user.id
    logger.info(f"[handle_prompt] Промпт от {user_id}: {text}")

    if len(text) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.", reply_markup=imagegen_menu_kb())
        return

    await message.answer("⏳ Генерация изображения...", reply_markup=imagegen_menu_kb())

    data = await state.get_data()
    aspect_ratio = data.get("aspect_ratio", "9:16")

    try:
        replicate.api_token = REPLICATE_API_TOKEN

        prediction = await replicate.predictions.async_create(
            model="google/imagen-4",
            input={
                "prompt": text,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "safety_filter_level": "block_medium_and_above",
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        )

        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)
            logger.debug(f"[handle_prompt] Ожидание... статус: {prediction.status}")

        if prediction.status == "failed":
            raise RuntimeError("Генерация не удалась.")

        output = prediction.output
        if isinstance(output, list) and output:
            image_url = output[0]
        elif isinstance(output, str):
            image_url = output
        else:
            raise ValueError("Некорректный формат output")

        logger.info(f"[handle_prompt] Успешно: {image_url}")
        await message.answer_photo(image_url, caption=f"✅ Ваше изображение:\n{text}", reply_markup=imagegen_menu_kb())

    except Exception as e:
        logger.exception(f"[handle_prompt] Ошибка генерации: {e}")
        await message.answer("❌ Произошла ошибка при генерации. Попробуйте позже.", reply_markup=imagegen_menu_kb())

    await state.clear()

# --- Основной запуск ---
async def main():
    logger.info("Запуск Telegram-бота...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(aspect_imagegen4, F.data.startswith("aspect_"), StateFilter(ImageGenState.AWAITING_ASPECT))
    dp.message.register(handle_prompt, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.message.register(go_main_menu, F.text == MAIN_MENU_BUTTON_TEXT)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
