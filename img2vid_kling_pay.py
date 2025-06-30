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

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_API_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или REPLICATE_API_TOKEN в .env файле")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Установка токена Replicate
replicate.api_token = REPLICATE_API_TOKEN

# Состояния FSM
class KlingVideoState(StatesGroup):
    waiting_image = State()
    waiting_prompt = State()

# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 Привет! Пришли изображение, которое будет стартовым кадром видео.")
    await state.set_state(KlingVideoState.waiting_image)

# Получение изображения
async def handle_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправь изображение.")
        return

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await state.update_data(image_url=image_url)
    await message.answer("✏️ Отлично! Теперь пришли описание сцены на английском.")
    await state.set_state(KlingVideoState.waiting_prompt)

# Получение текста (prompt) и генерация видео
async def handle_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Описание слишком короткое. Минимум 15 символов.")
        return

    data = await state.get_data()
    image_url = data.get("image_url")

    if not image_url:
        await message.answer("⚠️ Изображение не найдено. Начни заново: /start")
        return

    await message.answer("🎥 Генерируем видео... Это может занять пару минут.")

    try:
        prediction = await replicate.predictions.async_create(
            model="kwaivgi/kling-v2.1",
            input={
                "mode": "standard",
                "prompt": prompt,
                "duration": 5,
                "start_image": image_url,
                "negative_prompt": ""
            }
        )
        logger.info(f"Создан prediction: {prediction.id}")

        while prediction.status not in ("succeeded", "failed"):
            logger.info(f"Status: {prediction.status} — ждем 3 сек...")
            await asyncio.sleep(3)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            output = prediction.output
            video_url = None

            if isinstance(output, str) and output.startswith("http"):
                video_url = output
            elif isinstance(output, list):
                video_url = next((url for url in output if isinstance(url, str) and url.startswith("http")), None)

            if video_url:
                await message.answer_video(video_url, caption="✅ Готово! Вот твое видео.")
            else:
                logger.error(f"Неизвестный формат вывода: {output}")
                await message.answer("⚠️ Не удалось получить видео. Попробуй позже.")
        else:
            logger.error(f"Ошибка генерации: {prediction.error}")
            await message.answer("❌ Ошибка при генерации видео.")
    except Exception as e:
        logger.exception("Ошибка при генерации:")
        await message.answer("⚠️ Произошла ошибка при генерации видео.")

    await state.clear()

# Запуск бота
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_image, StateFilter(KlingVideoState.waiting_image))
    dp.message.register(handle_prompt, StateFilter(KlingVideoState.waiting_prompt))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
