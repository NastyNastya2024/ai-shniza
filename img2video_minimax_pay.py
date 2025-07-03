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

# Загрузка переменных из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Установка токена Replicate
replicate.api_token = REPLICATE_API_TOKEN

# Состояния бота
class VideoGenState(StatesGroup):
    waiting_image = State()
    waiting_prompt = State()

# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Видео-бот **Minimax** превращает изображение + текст в видео.\n\n"
        "📋 Возможности:\n"
        "- Анимирование кадра по описанию\n"
        "- Генерация реалистичных движений\n"
        "⚠️ Важно: генерация работает на английском языке.\n"
        "💰 Себестоимость генерации — ~$1.2\n\n"
        "📌 Начнем! Пришли изображение, с которого начнется видео."
    )
    await state.set_state(VideoGenState.waiting_image)

# Получение изображения
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправь изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Теперь пришли описание (prompt) для видео (на английском).")
    await state.set_state(VideoGenState.waiting_prompt)

# Получение промпта и генерация видео
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 10:
        await message.answer("❌ Слишком короткое описание. Минимум 10 символов.")
        return

    data = await state.get_data()
    image_url = data.get("image_url")

    if not image_url:
        await message.answer("⚠️ Изображение не найдено. Начни заново: /start")
        return

    await message.answer("🎬 Генерируем видео, это может занять несколько минут...")

    try:
        prediction = await replicate.predictions.async_create(
            model="minimax/video-01-live",
            input={
                "prompt": prompt,
                "prompt_optimizer": True,
                "first_frame_image": image_url,
            }
        )
        logger.info(f"Создан prediction: {prediction.id}")

        while prediction.status not in ("succeeded", "failed"):
            logger.info(f"Статус: {prediction.status} — ожидание 5 сек...")
            await asyncio.sleep(5)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            output_url = prediction.output
            if isinstance(output_url, str):
                await message.answer_video(output_url, caption="✅ Готово! Вот твое видео.")
            else:
                await message.answer("⚠️ Видео получено, но формат вывода непонятен.")
        else:
            logger.error(f"Ошибка генерации: {prediction.error}")
            await message.answer("❌ Ошибка генерации видео.")
    except Exception as e:
        logger.exception("Ошибка при вызове Replicate:")
        await message.answer("⚠️ Произошла ошибка при генерации видео.")

    await state.clear()

# Запуск бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image, StateFilter(VideoGenState.waiting_image))
    dp.message.register(handle_prompt, StateFilter(VideoGenState.waiting_prompt))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


