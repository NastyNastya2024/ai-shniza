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
class FluxKontextState(StatesGroup):
    WAITING_IMAGE = State()
    WAITING_PROMPT = State()

# --- Команда /start ---
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("👋 Привет! Отправь изображение, которое хочешь преобразовать.")
    await state.set_state(FluxKontextState.WAITING_IMAGE)

# --- Обработка изображения ---
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Теперь отправь описание (промпт), например: `Make this a 90s cartoon`")
    await state.set_state(FluxKontextState.WAITING_PROMPT)

# --- Обработка промпта и генерация ---
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    data = await state.get_data()
    image_url = data.get("image_url")

    if not image_url:
        await message.answer("❌ Изображение не найдено. Попробуй сначала с /start.")
        return

    await message.answer("⏳ Генерирую изображение...")

    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        seed = random.randint(0, 2**31 - 1)
        prediction = client.predictions.create(
            version="black-forest-labs/flux-kontext-pro",  # используйте актуальный version, если требуется
            input={
                "prompt": prompt,
                "input_image": image_url,
                "aspect_ratio": "match_input_image",
                "output_format": "jpg",
                "safety_tolerance": 2,
                "seed": seed
            }
        )
        logger.info(f"[handle_prompt] Prediction created: {prediction.id}")
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction.reload()
            logger.info(f"[handle_prompt] Status: {prediction.status}")
        if prediction.status == "succeeded" and prediction.output:
            output = prediction.output
            logger.info(f"[handle_prompt] Output: {output}")
            if isinstance(output, str) and (output.startswith("http://") or output.startswith("https://")):
                image_result_url = output
            elif isinstance(output, list) and output and (isinstance(output[0], str) and (output[0].startswith("http://") or output[0].startswith("https://"))):
                image_result_url = output[0]
            else:
                raise ValueError(f"Неверный результат от модели: {output}")
            await message.answer_photo(image_result_url, caption=f"✅ Готово!\n\n🔤 *Prompt:* {prompt}", parse_mode="Markdown")
        else:
            await message.answer("❌ Не удалось сгенерировать изображение. Попробуйте позже.")
            logger.error(f"[handle_prompt] Generation failed. Status: {prediction.status}, Output: {prediction.output}")
    except Exception:
        logger.exception("[handle_prompt] Ошибка генерации изображения")
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
    dp.message.register(handle_image, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.message.register(handle_prompt, StateFilter(FluxKontextState.WAITING_PROMPT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())