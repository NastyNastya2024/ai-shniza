import os
import logging
import asyncio
import replicate
import aiohttp
import ffmpeg

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Состояния FSM
class ImageGenState(StatesGroup):
    AWAITING_PROMPT = State()

class VoiceGenState(StatesGroup):
    AWAITING_TEXT = State()

# Обработка команды /start
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("👋 Привет! Команды:\n/start — начало\n/image — генерация изображения\n/voice — озвучка текста")
    await state.clear()

# Обработка команды /image
async def cmd_image(message: Message, state: FSMContext):
    await message.answer("✍️ Отправь описание на английском для генерации изображения:")
    await state.set_state(ImageGenState.AWAITING_PROMPT)

# Обработка команды /voice
async def cmd_voice(message: Message, state: FSMContext):
    await message.answer("🗣 Отправь текст (на английском), который нужно озвучить.")
    await state.set_state(VoiceGenState.AWAITING_TEXT)

# Обработка текста для изображения
async def handle_image_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 15:
        await message.answer("❌ Минимум 15 символов.")
        return

    await message.answer("🎨 Генерация изображения...")
    replicate.api_token = REPLICATE_API_TOKEN

    try:
        prediction = await replicate.predictions.async_create(
            model="google/imagen-4",
            input={
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "output_format": "png",
                "guidance_scale": 7.5,
                "num_inference_steps": 50,
            }
        )

        while prediction.status not in ("succeeded", "failed"):
            await asyncio.sleep(2)
            prediction = await replicate.predictions.async_get(prediction.id)

        if prediction.status == "succeeded":
            image_url = prediction.output[0]
            await message.answer_photo(image_url, caption="✅ Готово!")
        else:
            await message.answer("❌ Ошибка генерации изображения.")

    except Exception:
        logger.exception("Ошибка генерации:")
        await message.answer("⚠️ Ошибка при генерации.")
    await state.clear()

# Обработка текста для голосового сообщения
async def handle_voice_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий.")
        return

    await message.answer("🎤 Генерация озвучки...")

    replicate.api_token = REPLICATE_API_TOKEN
    try:
        output = replicate.run(
            "resemble-ai/chatterbox",
            input={
                "prompt": text,
                "seed": 0,
                "cfg_weight": 0.5,
                "temperature": 0.8,
                "exaggeration": 0.5
            }
        )
        logger.info(f"Output from replicate.run: {output} (type: {type(output)})")

        # Получаем audio_url из объекта output
        if hasattr(output, "url"):
            audio_url = output.url
        elif isinstance(output, str):
            audio_url = output
        elif isinstance(output, list) and output:
            audio_url = output[0]
        elif isinstance(output, dict) and "audio_url" in output:
            audio_url = output["audio_url"]
        else:
            raise ValueError("Не удалось получить URL аудио из вывода модели")

        logger.info(f"Audio URL: {audio_url}")

        # Скачиваем .wav файл
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    raise Exception("Ошибка скачивания аудио")
                with open("output.wav", "wb") as f:
                    f.write(await resp.read())

        # Конвертация в .ogg (Opus) для Telegram voice
        (
            ffmpeg
            .input("output.wav")
            .output("voice.ogg", format='opus', audio_bitrate='64k', acodec='libopus')
            .overwrite_output()
            .run()
        )

        # Отправка voice
        voice = FSInputFile("voice.ogg")
        await message.answer_voice(voice)

    except Exception:
        logger.exception("Ошибка озвучки:")
        await message.answer("⚠️ Ошибка генерации аудио.")

    finally:
        if os.path.exists("output.wav"):
            os.remove("output.wav")
        if os.path.exists("voice.ogg"):
            os.remove("voice.ogg")

    await state.clear()

# Запуск бота
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_image, Command("image"))
    dp.message.register(cmd_voice, Command("voice"))
    dp.message.register(handle_image_prompt, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.message.register(handle_voice_text, StateFilter(VoiceGenState.AWAITING_TEXT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
