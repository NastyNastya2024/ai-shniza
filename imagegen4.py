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

# --- /start ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    logger.info(f"[cmd_start] Пользователь {message.from_user.id} вызвал /start")

    welcome_text = (
        "🖼 *Image Gen Bot* (Google Imagen 4) — генерация изображений по текстовому описанию на английском языке.\n\n"
        "📋 *Возможности:*\n"
        "- Генерация реалистичных и художественных изображений\n"
        "- Поддержка различных соотношений сторон (1:1, 9:16, 16:9)\n"
        "- Высокое качество и детализация\n\n"
        "⚠️ *Важно:*\n"
        "- Промпт (описание) — только на английском языке\n"
        "- Минимум 15 символов\n"
        "- 💰 Стоимость: бесплатно\n\n"
        "⬇️ Выберите соотношение сторон:"
    )

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=aspect_ratio_kb())
    await state.set_state(ImageGenState.AWAITING_ASPECT)

# --- Обработка выбора соотношения сторон ---
async def aspect_selected(callback: CallbackQuery, state: FSMContext):
    aspect_value = callback.data.split("_")[1]
    await state.update_data(aspect_ratio=aspect_value)
    logger.info(f"[aspect_selected] Пользователь {callback.from_user.id} выбрал аспект {aspect_value}")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отправьте описание (промпт) на английском языке (минимум 15 символов):")
    await state.set_state(ImageGenState.AWAITING_PROMPT)
    await callback.answer()

# --- Обработка промпта ---
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"[handle_prompt] Промпт от {user_id}: {prompt}")

    if len(prompt) < 15:
        await message.answer("❌ Описание должно быть не короче 15 символов.")
        return

    await message.answer("⏳ Генерация изображения...")

    data = await state.get_data()
    aspect_ratio = data.get("aspect_ratio", "9:16")

    try:
        replicate.api_token = REPLICATE_API_TOKEN

        prediction = await replicate.predictions.async_create(
            model="google/imagen-4",
            input={
                "prompt": prompt,
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

    # Регистрация хендлеров
    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(aspect_selected, F.data.startswith("aspect_"), StateFilter(ImageGenState.AWAITING_ASPECT))
    dp.message.register(handle_prompt, StateFilter(ImageGenState.AWAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
