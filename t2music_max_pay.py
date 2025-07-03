import os
import logging
import asyncio
import replicate
import aiohttp
import ffmpeg

from replicate.helpers import FileOutput
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Состояния FSM
class VoiceGenState(StatesGroup):
    AWAITING_BITRATE = State()
    AWAITING_SAMPLE_RATE = State()
    AWAITING_TEXT = State()

# Inline-кнопки битрейта
bitrate_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="32000 — низкое", callback_data="bitrate_32000")],
        [InlineKeyboardButton(text="64000 — среднее", callback_data="bitrate_64000")],
        [InlineKeyboardButton(text="128000 — хорошее", callback_data="bitrate_128000")],
        [InlineKeyboardButton(text="256000 — высокое", callback_data="bitrate_256000")],
    ]
)

# Inline-кнопки sample rate
sample_rate_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="16000 Гц — разговорный", callback_data="sr_16000")],
        [InlineKeyboardButton(text="24000 Гц — улучшенный", callback_data="sr_24000")],
        [InlineKeyboardButton(text="32000 Гц — нормальный", callback_data="sr_32000")],
        [InlineKeyboardButton(text="44100 Гц — CD качество", callback_data="sr_44100")],
    ]
)

# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я голосовой бот на основе модели MiniMax Music-01.\n\n"
        "🎶 Превращаю английский текст в озвученную музыку .\n\n"
        "📋 Что я умею:\n"
        "- Генерировать музыку по тексту\n"
        "- Поддерживаю выбор качества аудио\n"
        "- Поддерживаю выбор частоты \n\n"
        "⚠️ ВАЖНО: генерация только женским голосом в стиле диско на английском языке.\n"
        "🎛 Себестоимость $0.2 (комиссии нет)",
        reply_markup=bitrate_kb
    )
    await state.set_state(VoiceGenState.AWAITING_BITRATE)

# Обработка inline-выбора битрейта
async def handle_bitrate_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bitrate = int(callback.data.split("_")[1])
    await state.update_data(bitrate=bitrate)
    await callback.message.edit_text("Выбранный битрейт: {}. Теперь выбери sample rate:".format(bitrate), reply_markup=sample_rate_kb)
    await state.set_state(VoiceGenState.AWAITING_SAMPLE_RATE)

# Обработка inline-выбора sample rate
async def handle_sample_rate_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sample_rate = int(callback.data.split("_")[1])
    await state.update_data(sample_rate=sample_rate)
    await callback.message.edit_text(
    "✅ Параметры выбраны.\n\n"
    "Теперь отправь текст (на английском), который нужно озвучить.\n\n"
)
    await state.set_state(VoiceGenState.AWAITING_TEXT)

# Обработка текста
async def handle_voice_text(message: Message, state: FSMContext):
    data = await state.get_data()
    bitrate = data.get("bitrate", 256000)
    sample_rate = data.get("sample_rate", 44100)

    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий.")
        return

    await message.answer("🎵 Генерация музыки по тексту...")

    replicate.api_token = REPLICATE_API_TOKEN

    try:
        output = replicate.run(
            "minimax/music-01",
            input={
                "lyrics": text,
                "bitrate": bitrate,
                "sample_rate": sample_rate,
                "song_file": "https://replicate.delivery/pbxt/M9zum1Y6qujy02jeigHTJzn0lBTQOemB7OkH5XmmPSC5OUoO/MiniMax-Electronic.wav"
            }
        )

        logger.info(f"RAW Output from replicate: {output} (type: {type(output)})")

        if isinstance(output, FileOutput):
            audio_url = str(output)
        elif isinstance(output, str):
            audio_url = output
        elif isinstance(output, list) and output:
            audio_url = output[0]
        else:
            raise ValueError("Не удалось получить ссылку на аудио.")

        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    raise Exception("Ошибка скачивания аудио")
                with open("output.mp3", "wb") as f:
                    f.write(await resp.read())

        (
            ffmpeg
            .input("output.mp3")
            .output("voice.ogg", format='opus', audio_bitrate='64k', acodec='libopus')
            .overwrite_output()
            .run()
        )

        voice = FSInputFile("voice.ogg")
        await message.answer_voice(voice)

    except Exception:
        logger.exception("Ошибка генерации аудио:")
        await message.answer("⚠️ Ошибка генерации аудио.")
    finally:
        for file in ["output.mp3", "voice.ogg"]:
            if os.path.exists(file):
                os.remove(file)

    await state.clear()

# Запуск бота
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(handle_bitrate_callback, F.data.startswith("bitrate_"))
    dp.callback_query.register(handle_sample_rate_callback, F.data.startswith("sr_"))
    dp.message.register(handle_voice_text, StateFilter(VoiceGenState.AWAITING_TEXT))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
