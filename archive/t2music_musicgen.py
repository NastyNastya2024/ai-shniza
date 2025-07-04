import os
import asyncio
import logging
from dotenv import load_dotenv
import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

REPLICATE_MODEL_VERSION = "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

HEADERS = {
    "Authorization": f"Token {REPLICATE_API_TOKEN}",
    "Content-Type": "application/json"
}

MODEL_VERSIONS = {
    "stereo-large": "Stereo Large",
    "stereo-melody-large": "Stereo Melody Large",
    "melody-large": "Melody Large",
    "large": "Large"
}

NORMALIZATION_STRATEGIES = {
    "loudness": "Loudness",
    "clip": "Clip",
    "peak": "Peak",
    "rms": "RMS"
}

class MusicGenStates(StatesGroup):
    choosing_model = State()
    choosing_normalization = State()
    waiting_for_prompt = State()

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """
    Приветственное сообщение с описанием бота и инструкцией по выбору модели.
    """
    await state.clear()
    welcome_text = (
        "👋 Привет! Я MusicGen — бот для генерации музыки по твоим текстовым описаниям.\n\n"
        "💡 Что может MusicGen:\n"
        "- Генерировать музыку по твоему промпту (описанию)\n"
        "- Поддерживает разные модели: от стерео до мелодий\n"
        "- Позволяет выбрать стратегию нормализации звука\n\n"
        "⚠️ ВАЖНО: промпт должен быть на английском языке.\n\n"
        "⏳ Одна генерация занимает около 20-30 секунд.\n"
        "💰 Примерная себестоимость одной генерации — около $1.\n\n"
    )

    model_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=key)] for key, name in MODEL_VERSIONS.items()
        ]
    )
    await message.answer(welcome_text, reply_markup=model_keyboard)
    await state.set_state(MusicGenStates.choosing_model)

@dp.callback_query(MusicGenStates.choosing_model)
async def model_chosen(query: CallbackQuery, state: FSMContext):
    selected_model = query.data
    if selected_model not in MODEL_VERSIONS:
        await query.answer("Некорректный выбор модели, попробуй снова.", show_alert=True)
        return

    await state.update_data(model_version=selected_model)
    await query.answer(f"Выбрана модель: {MODEL_VERSIONS[selected_model]}")

    norm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=key)] for key, name in NORMALIZATION_STRATEGIES.items()
        ]
    )
    await query.message.answer(
        "🎚 Теперь выбери стратегию нормализации звука:\n"
        "- loudness: нормализация по громкости\n"
        "- clip: обрезание пиков\n"
        "- peak: пиковая нормализация\n"
        "- rms: нормализация по средней мощности\n\n"
        "Выбор стратегии:",
        reply_markup=norm_keyboard
    )
    await state.set_state(MusicGenStates.choosing_normalization)

@dp.callback_query(MusicGenStates.choosing_normalization)
async def normalization_chosen(query: CallbackQuery, state: FSMContext):
    selected_norm = query.data
    if selected_norm not in NORMALIZATION_STRATEGIES:
        await query.answer("Некорректный выбор нормализации, попробуй снова.", show_alert=True)
        return

    await state.update_data(normalization_strategy=selected_norm)
    await query.answer(f"Выбрана нормализация: {NORMALIZATION_STRATEGIES[selected_norm]}")

    await query.message.answer(
        "✍️ Теперь отправь мне музыкальный промпт для генерации.\n"
        "Пример (на английском): \"A calm piano melody with ambient background\""
    )
    await state.set_state(MusicGenStates.waiting_for_prompt)

@dp.message(MusicGenStates.waiting_for_prompt)
async def receive_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if len(prompt) < 5:
        await message.answer("❌ Слишком короткий промпт. Попробуй ещё раз.")
        return

    data = await state.get_data()
    model_version = data.get("model_version", "stereo-large")
    normalization_strategy = data.get("normalization_strategy", "peak")

    await message.answer("🎶 Генерация музыки... Подожди 20-30 секунд...")

    async with aiohttp.ClientSession() as session:
        prediction_payload = {
            "version": REPLICATE_MODEL_VERSION,
            "input": {
                "prompt": prompt,
                "duration": 8,
                "output_format": "mp3",
                "model_version": model_version,
                "classifier_free_guidance": 3,
                "temperature": 1,
                "top_k": 250,
                "top_p": 0,
                "continuation": False,
                "multi_band_diffusion": False,
                "normalization_strategy": normalization_strategy
            }
        }

        async with session.post(REPLICATE_API_URL, json=prediction_payload, headers=HEADERS) as response:
            prediction = await response.json()
            prediction_id = prediction.get("id")
            if not prediction_id:
                await message.answer("❌ Ошибка запуска генерации.")
                logging.error(f"Ошибка запуска генерации: {prediction}")
                return

        output_url = None
        for _ in range(40):
            async with session.get(f"{REPLICATE_API_URL}/{prediction_id}", headers=HEADERS) as poll_response:
                result = await poll_response.json()
                status = result.get("status")
                if status == "succeeded":
                    output_url = result.get("output")
                    break
                elif status == "failed":
                    await message.answer("❌ Генерация провалилась. Попробуй ещё раз.")
                    return
            await asyncio.sleep(1)

        if not output_url:
            await message.answer("❌ Не удалось получить ссылку на аудио.")
            return

        filename = "generated_track.mp3"
        async with session.get(output_url) as music_response:
            if music_response.status == 200:
                with open(filename, "wb") as f:
                    f.write(await music_response.read())
            else:
                await message.answer("❌ Ошибка скачивания аудио.")
                return

        await message.answer_audio(FSInputFile(filename), caption="🎧 Вот твоя музыка!")
        os.remove(filename)

    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
