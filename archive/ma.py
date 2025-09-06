import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from models.gpt import (
    PromptTranslationState, 
    cmd_start as gpt_start, 
    handle_russian_prompt
)
from models.imagegen4 import ImageGenState
from models.kling import (
    KlingVideoState,
    cmd_start as kling_start,
    handle_image,
    handle_mode_selection,
    handle_duration_selection,
    handle_prompt,
    handle_confirm_generation
)
from models.minimax import (
    VideoGenState,
    cmd_start as minimax_start,
    handle_image as minimax_handle_image,
    handle_prompt as minimax_handle_prompt,
    confirm_generation as minimax_confirm_generation
)
from models.musicgen import (
    MusicGenStates,
    start_handler as musicgen_start,
    model_chosen,
    normalization_chosen,
    receive_prompt
)

from models.seedance import (
    VideoGenState as SeedanceState,
    cmd_start as seedance_start,
    handle_image as seedance_handle_image,
    handle_prompt as seedance_handle_prompt,
    handle_duration,
    handle_resolution,
    handle_aspect_ratio,
    handle_camera_fixed,
    handle_confirm_generation
)
from models.veo3 import (
    Veo3State,
    cmd_start as veo3_start,
    handle_prompt as veo3_handle_prompt,
    confirm_generation as veo3_confirm_generation
)



# === Настройки ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tg_bot")

# === FSM состояния ===
class MenuState(StatesGroup):
    generation = State()
    image_menu = State()
    image_text_menu = State()
    video_menu = State()
    video_image_menu = State()
    music_menu = State()

# === Клавиатуры ===
def main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎨 Генерация")],
        [KeyboardButton(text="🔤 Перевод")],
        [KeyboardButton(text="📊 Баланс")]
    ], resize_keyboard=True)


def generation_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🖼 Картинка"), KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="🎵 Музыка")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)


def image_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🖋 Картинка из текста")],
        [KeyboardButton(text="🖼 Картинка из картинки")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)


def image_text_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Ideogram.py"), KeyboardButton(text="Imagegen4.py")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)

def video_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📄 Видео из текста")],
        [KeyboardButton(text="🖼 Видео из картинки")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)

def video_image_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Kling"), KeyboardButton(text="Minimax")],
        [KeyboardButton(text="Seedance")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)

def music_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="MusicMax"), KeyboardButton(text="MusicGen")],
        [KeyboardButton(text="Chatterbox")],
        [KeyboardButton(text="Главное меню")]
    ], resize_keyboard=True)

# === Импорт моделей ===
from models import (
    ideogram,
    imagegen4,
    flux,
    veo3,
    kling,
    minimax,
    seedance,
    musicgen,
    chatterbox,
    gpt
)

# === Основной роутер ===
router = Router()

# === Основные хендлеры ===
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} начал работу")
    try:
        photo = InputFile("welcome.jpg")
        await message.answer_photo(photo, caption=f"👋 Привет, {message.from_user.first_name}!\nДобро пожаловать!")
    except Exception as e:
        logger.warning(f"Ошибка welcome.jpg: {e}")
        await message.answer(f"👋 Привет, {message.from_user.first_name}!\n(Изображение недоступно)")
    await message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await state.clear()

@router.message(F.text == "Главное меню")
async def to_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы в главном меню", reply_markup=main_menu_kb())

@router.message(F.text == "🎨 Генерация")
async def generation_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.generation)
    await message.answer("Что вы хотите сгенерировать?", reply_markup=generation_kb())

@router.message(F.text == "🖼 Картинка")
async def image_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.image_menu)
    await message.answer("Выберите тип генерации картинки:", reply_markup=image_menu_kb())

@router.message(F.text == "🖋 Картинка из текста")
async def image_text_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.image_text_menu)
    await message.answer("Выберите модель:", reply_markup=image_text_menu_kb())

@router.message(F.text == "Ideogram.py")
async def run_ideogram_menu(message: Message, state: FSMContext):
    await ideogram.cmd_start(message, state)

@router.message(F.text == "Imagegen4.py")
async def run_imagegen4(message: Message, state: FSMContext):
    await imagegen4.cmd_start(message, state)

@router.message(F.text == "🖼 Картинка из картинки")
async def run_flux(message: Message, state: FSMContext):
    await flux.cmd_start(message, state)

@router.message(F.text == "🎬 Видео")
async def video_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.video_menu)
    await message.answer("Выберите тип видео:", reply_markup=video_menu_kb())

@router.message(F.text == "📄 Видео из текста")
async def run_veo3(message: Message, state: FSMContext):
    await veo3.cmd_start(message, state)

@router.message(F.text == "🖼 Видео из картинки")
async def video_img_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.video_image_menu)
    await message.answer("Выберите модель:", reply_markup=video_image_menu_kb())

@router.message(F.text == "Kling")
async def run_kling(message: Message, state: FSMContext):
    await kling.cmd_start(message, state)

@router.message(F.text == "Minimax")
async def run_minimax(message: Message, state: FSMContext):
    await minimax.cmd_start(message, state)

@router.message(F.text == "Seedance")
async def run_seedance(message: Message, state: FSMContext):
    await seedance.cmd_start(message, state)

@router.message(F.text == "🎵 Музыка")
async def music_menu(message: Message, state: FSMContext):
    await state.set_state(MenuState.music_menu)
    await message.answer("Выберите модель:", reply_markup=music_menu_kb())

@router.message(F.text == "MusicMax")
async def run_musicmax(message: Message, state: FSMContext):
    await musicmax.cmd_start(message, state)

@router.message(F.text == "MusicGen")
async def run_musicgen(message: Message, state: FSMContext):
    await musicgen.cmd_start(message, state)

@router.message(F.text == "Chatterbox")
async def run_chatterbox(message: Message, state: FSMContext):
    await chatterbox.cmd_start(message, state)

@router.message(F.text == "🔤 Перевод")
async def translate_dummy(message: Message):
    await message.answer("Пример перевода: Hello → Привет")

@router.message(F.text == "📊 Баланс")
async def balance_dummy(message: Message):
    await message.answer("Ваш баланс: 100 💰")

# === Запуск ===
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("❌ Переменные окружения не заданы")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(router)

    # Регистрация колбэков и хендлеров Ideogram FSM
    dp.callback_query.register(
        ideogram.handle_aspect_ideogram,
        F.data.startswith("ideogram_aspect_"),
        StateFilter(ideogram.ImageGenState.SELECTING_ASPECT)
    )
    dp.callback_query.register(
        ideogram.handle_style_aspect_ideogram,
        F.data.startswith("ideogram_style_"),
        StateFilter(ideogram.ImageGenState.SELECTING_STYLE)
    )
    dp.message.register(
        ideogram.handle_prompt_aspect_ideogram,
        StateFilter(ideogram.ImageGenState.AWAITING_PROMPT)
    )
    
    # ✅ Регистрация хендлеров GPT FSM (перевод текста)
    dp.message.register(
        gpt_start,
        F.text == "🔤 Перевод"
    )
    dp.message.register(
        handle_russian_prompt,
        StateFilter(PromptTranslationState.WAITING_RU_PROMPT)
    )

    # Регистрация колбэков и хендлеров Chatterbox FSM
    dp.message.register(
        chatterbox.cmd_start,
        F.text == "Chatterbox"
    )
    dp.callback_query.register(
        chatterbox.choose_temperature,
        F.data.startswith("temp_"),
        StateFilter(chatterbox.VoiceGenState.CHOOSE_TEMPERATURE)
    )
    dp.callback_query.register(
        chatterbox.choose_seed,
        F.data.startswith("seed_"),
        StateFilter(chatterbox.VoiceGenState.CHOOSE_SEED)
    )
    dp.message.register(
        chatterbox.handle_voice_text,
        StateFilter(chatterbox.VoiceGenState.AWAITING_TEXT)
    )
    
    
    # ✅ Регистрация хендлеров Minimax FSM
    dp.message.register(
        minimax_start,
        F.text == "Minimax"
    )
    dp.message.register(
        minimax_handle_image,
        StateFilter(VideoGenState.waiting_image)
    )
    dp.message.register(
        minimax_handle_prompt,
        StateFilter(VideoGenState.waiting_prompt)
    )
    dp.callback_query.register(
        minimax_confirm_generation,
        F.data == "confirm_generation",
        StateFilter(VideoGenState.confirming_payment)
    )
    
        
    
    # ✅ Регистрация хендлеров Seedance FSM
    dp.message.register(
        seedance_start,
        F.text == "Seedance"
    )
    dp.message.register(
        seedance_handle_image,
        StateFilter(SeedanceState.waiting_image)
    )
    dp.message.register(
        seedance_handle_prompt,
        StateFilter(SeedanceState.waiting_prompt)
    )
    dp.callback_query.register(
        handle_duration,
        StateFilter(SeedanceState.waiting_duration)
    )
    dp.callback_query.register(
        handle_resolution,
        StateFilter(SeedanceState.waiting_resolution)
    )
    dp.callback_query.register(
        handle_aspect_ratio,
        StateFilter(SeedanceState.waiting_aspect_ratio)
    )
    dp.callback_query.register(
        handle_camera_fixed,
        StateFilter(SeedanceState.waiting_camera_fixed)
    )
    dp.callback_query.register(
        handle_confirm_generation,
        F.data == "confirm_generation",
        StateFilter(SeedanceState.confirm_pending)
    )



    # ✅ Регистрация хендлеров Kling FSM
    dp.message.register(
        kling_start,
        F.text == "Kling"
    )
    dp.message.register(
        handle_image,
        StateFilter(KlingVideoState.waiting_image)
    )
    dp.callback_query.register(
        handle_mode_selection,
        F.data.startswith("mode_"),
        StateFilter(KlingVideoState.waiting_mode)
    )
    dp.callback_query.register(
        handle_duration_selection,
        F.data.startswith("duration_"),
        StateFilter(KlingVideoState.waiting_duration)
    )
    dp.message.register(
        handle_prompt,
        StateFilter(KlingVideoState.waiting_prompt)
    )
    dp.callback_query.register(
        handle_confirm_generation,
        F.data == "confirm_gen",
        StateFilter(KlingVideoState.confirm_pending)
    )
    
    # ✅ Регистрация хендлеров MusicGen FSM
    dp.message.register(
        musicgen_start,
        F.text == "MusicGen"
    )
    dp.callback_query.register(
        model_chosen,
        StateFilter(MusicGenStates.choosing_model)
    )
    dp.callback_query.register(
        normalization_chosen,
        StateFilter(MusicGenStates.choosing_normalization)
    )
    dp.message.register(
        receive_prompt,
        StateFilter(MusicGenStates.waiting_for_prompt)
    )
    
    # ✅ Регистрация хендлеров MusicGen FSM
    dp.message.register(
        musicgen_start,
        F.text == "MusicGen"
    )
    dp.callback_query.register(
        model_chosen,
        StateFilter(MusicGenStates.choosing_model)
    )
    dp.callback_query.register(
        normalization_chosen,
        StateFilter(MusicGenStates.choosing_normalization)
    )
    dp.message.register(
        receive_prompt,
        StateFilter(MusicGenStates.waiting_for_prompt)
    )
    
    # ✅ Регистрация хендлеров Veo3 FSM
    dp.message.register(
        veo3_start,
        F.text == "Veo3"
    )
    dp.message.register(
        veo3_handle_prompt,
        StateFilter(Veo3State.waiting_for_prompt)
    )
    dp.callback_query.register(
        veo3_confirm_generation,
        F.data == "confirm_generation",
        StateFilter(Veo3State.confirming_payment)
    )


    # ✅ Регистрация хендлеров Flux FSM
    dp.message.register(
        flux.handle_image_flux,
        StateFilter(flux.FluxKontextState.WAITING_IMAGE)
    )
    dp.callback_query.register(
        flux.handle_aspect_ratio,
        F.data.startswith("aspect_"),
        StateFilter(flux.FluxKontextState.WAITING_ASPECT_RATIO)
    )
    dp.message.register(
        flux.handle_prompt,
        StateFilter(flux.FluxKontextState.WAITING_PROMPT)
    )

    logger.info("🤖 Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
