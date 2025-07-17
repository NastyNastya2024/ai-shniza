import os
import logging
import asyncio
import replicate
import aiohttp
import ffmpeg

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from keyboards import (
    MAIN_MENU_BUTTON_TEXT,
    main_menu_kb,
    universal_back_kb,
    chatterbox_menu_kb,
)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# Состояния FSM
class VoiceGenState(StatesGroup):
    CHOOSE_TEMPERATURE = State()
    CHOOSE_SEED = State()
    AWAITING_TEXT = State()

# Инлайн-кнопки
def temperature_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Низкий (0.2)", callback_data="temp_0.2")],
        [InlineKeyboardButton(text="Средний (0.5)", callback_data="temp_0.5")],
        [InlineKeyboardButton(text="Высокий (0.8)", callback_data="temp_0.8")]
    ])

def seed_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Случайность 1", callback_data="seed_0")],
        [InlineKeyboardButton(text="Случайность 2", callback_data="seed_42")],
        [InlineKeyboardButton(text="Случайность 3", callback_data="seed_123")]
    ])

# /start
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    try:
        photo = FSInputFile("welcome.jpg")
        await message.answer_photo(photo, caption="👋 Добро пожаловать в Chatterbox!")
    except Exception as e:
        logger.warning(f"Ошибка с welcome.jpg: {e}")
        await message.answer("👋 Добро пожаловать в Chatterbox!")

    await message.answer(
        "🧠 Ты выбрал модель **Chatterbox** — она предназначена для создания реалистичной озвучки текста, "
        "имитируя живую речь с оттенками эмоций и интонации.\n\n"
        "📌 **Важно:**\n"
        "- Модель работает **только с текстом на английском языке**\n"
        "- Озвучка **бесплатна**\n"
        "- Чтобы задать **пол чтеца**, добавь к началу текста:\n"
        "  👉 `Male voice:` или `Female voice:`\n\n"
        "🎛 Сначала выбери стиль подачи текста:",
        reply_markup=temperature_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(VoiceGenState.CHOOSE_TEMPERATURE)

# temperature
async def choose_temperature(callback: CallbackQuery, state: FSMContext):
    temperature = float(callback.data.split("_")[1])
    await state.update_data(temperature=temperature)
    await callback.message.edit_text(
        "🎲 Теперь выбери вариант генерации (влияет на случайность результата):",
        reply_markup=seed_keyboard()
    )
    await state.set_state(VoiceGenState.CHOOSE_SEED)
    await callback.answer()

# seed
async def choose_seed(callback: CallbackQuery, state: FSMContext):
    seed = int(callback.data.split("_")[1])
    await state.update_data(seed=seed)
    await callback.message.edit_text(
        "✍️ Отправь текст на английском, который нужно озвучить.\n\n"
        "Пример: `Hello! I’m your friendly voice bot.`",
        parse_mode="Markdown"
    )
    await state.set_state(VoiceGenState.AWAITING_TEXT)

# генерация
async def handle_voice_text(message: Message, state: FSMContext):
    if message.text == MAIN_MENU_BUTTON_TEXT:
        await state.clear()
        await message.answer("Вы вернулись в главное меню.", reply_markup=main_menu_kb())
        return

    if message.text == "🔁 Повторить генерацию":
        await cmd_start(message, state)
        return

    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий.", reply_markup=universal_back_kb())
        return

    await message.answer("🎤 Генерация озвучки...")

    replicate.api_token = REPLICATE_API_TOKEN
    data = await state.get_data()
    temperature = data.get("temperature", 0.5)
    seed = data.get("seed", 0)

    try:
        output = replicate.run(
            "resemble-ai/chatterbox",
            input={
                "prompt": text,
                "seed": seed,
                "cfg_weight": 0.5,
                "temperature": temperature,
                "exaggeration": 0.5
            }
        )

        if isinstance(output, str):
            audio_url = output
        elif isinstance(output, list) and output:
            audio_url = output[0]
        elif isinstance(output, dict) and "audio_url" in output:
            audio_url = output["audio_url"]
        else:
            raise ValueError("Невозможно извлечь URL аудио")

        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    raise Exception("Ошибка скачивания аудио")
                with open("output.wav", "wb") as f:
                    f.write(await resp.read())

        (
            ffmpeg
            .input("output.wav")
            .output("voice.ogg", format='opus', audio_bitrate='64k', acodec='libopus')
            .overwrite_output()
            .run()
        )

        voice = FSInputFile("voice.ogg")
        await message.answer_voice(voice, reply_markup=chatterbox_menu_kb())

    except Exception:
        logger.exception("Ошибка озвучки:")
        await message.answer("⚠️ Ошибка генерации аудио.", reply_markup=chatterbox_menu_kb())
    finally:
        for f in ["output.wav", "voice.ogg"]:
            if os.path.exists(f):
                os.remove(f)

    await state.clear()

# "🏠 Главное меню" — универсально
async def go_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())

# main()
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 🟢 Главное меню обрабатывается на ЛЮБОЕ состояние
    dp.message.register(go_main_menu, F.text == MAIN_MENU_BUTTON_TEXT, StateFilter("*"))

    dp.message.register(cmd_start, Command("start"))
    dp.callback_query.register(choose_temperature, F.data.startswith("temp_"), StateFilter(VoiceGenState.CHOOSE_TEMPERATURE))
    dp.callback_query.register(choose_seed, F.data.startswith("seed_"), StateFilter(VoiceGenState.CHOOSE_SEED))
    dp.message.register(handle_voice_text, StateFilter(VoiceGenState.AWAITING_TEXT))

    logging.info("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
