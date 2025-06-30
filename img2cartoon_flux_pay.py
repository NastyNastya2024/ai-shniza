import os
import asyncio
import logging
import replicate
import aiohttp
import ffmpeg
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
class VoiceGenState(StatesGroup):
    WAITING_TEXT = State()

# Хендлер старта
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("👋 Привет! Отправь мне текст, и я озвучу его.")
    await state.set_state(VoiceGenState.WAITING_TEXT)

# Основной хендлер генерации голоса
async def handle_voice_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий.")
        return

    await message.answer("🎤 Генерация озвучки...")

    replicate.api_token = REPLICATE_API_TOKEN

    try:
        prediction = await replicate.predictions.async_create(
            model="resemble-ai/chatterbox",
            input={
                "prompt": text,
                "seed": 0,
                "cfg_weight": 0.5,
                "temperature": 0.8,
                "exaggeration": 0.5,
            }
        )

        logger.info(f"[handle_voice_text] Prediction created: {prediction.id}")

        # Ждём завершения предсказания
        while prediction.status not in ("succeeded", "failed", "canceled"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)
            logger.info(f"[handle_voice_text] Status: {prediction.status}")

        if prediction.status == "succeeded" and prediction.output:
            output = prediction.output
            logger.info(f"[handle_voice_text] Output: {output}")

            # Проверяем формат вывода
            if isinstance(output, str) and output.startswith("http"):
                audio_url = output
            elif isinstance(output, list) and output and isinstance(output[0], str) and output[0].startswith("http"):
                audio_url = output[0]
            else:
                raise ValueError(f"Неверный формат аудио вывода: {output}")

            # Скачиваем аудио
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Ошибка загрузки аудио: HTTP {resp.status}")
                    with open("output.wav", "wb") as f:
                        f.write(await resp.read())

            # Конвертируем в .ogg
            (
                ffmpeg
                .input("output.wav")
                .output("voice.ogg", format='opus', audio_bitrate='64k', acodec='libopus')
                .overwrite_output()
                .run()
            )

            # Отправляем пользователю
            voice = FSInputFile("voice.ogg")
            await message.answer_voice(voice)

        else:
            await message.answer("❌ Не удалось сгенерировать аудио. Попробуйте позже.")
            logger.error(f"[handle_voice_text] Ошибка генерации. Status: {prediction.status}, Output: {prediction.output}")

    except Exception as e:
        logger.exception("[handle_voice_text] Ошибка генерации аудио")
        await message.answer("⚠️ Ошибка при генерации озвучки.")
    finally:
        if os.path.exists("output.wav"): os.remove("output.wav")
        if os.path.exists("voice.ogg"): os.remove("voice.ogg")

    await state.clear()

# Запуск бота
async def main():
    logger.info("Запуск Telegram-бота...")

    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        raise EnvironmentError("BOT_TOKEN или REPLICATE_API_TOKEN не установлены в .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_voice_text, F.text, state=VoiceGenState.WAITING_TEXT)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
