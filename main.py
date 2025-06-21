import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from sqlalchemy.orm import Session

from database import init_db, SessionLocal, User
from bot.config import PRICE_PER_GENERATION, PAYMENT_LINK, ALLOW_GENERATION_WHEN_ZERO, NO_GENERATION_MESSAGE

from models.model_video_1 import start_video_generation, setup_video_handlers
from models.model_video_2 import setup_veo3_handlers
from models.model_video_3 import start_pixverse_generation, setup_pixverse_handlers

# ✅ Импортируем генераторы картинок
from models.model_image_1 import start_image_generation_1, setup_imagegen1_handlers
from models.model_image_2 import setup_imagegen2_handlers
#from models.model_image_3 import start_image_generation_3

# --- Регистрация обработчиков видео
setup_video_handlers(dp)
setup_veo3_handlers(dp)
setup_pixverse_handlers(dp)
setup_imagegen1_handlers(dp)
setup_imagegen2_handlers(dp)


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

class GenerationStates(StatesGroup):
    waiting_for_image_params = State()
    waiting_for_video_params = State()
    waiting_for_audio_params = State()
    waiting_for_3d_params = State()

def start_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎨 Генерация")],
        [KeyboardButton(text="📊 Баланс")]
    ], resize_keyboard=True)

def balance_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

def payment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Пополнить баланс", url=PAYMENT_LINK)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

async def get_or_create_user(user_id: int, username: str):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        user = User(
            telegram_id=user_id,
            username=username,
            balance=0  # баланс в рублях
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

async def cmd_start(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer("✅ Старт принят!")
    await message.answer(
        f"Привет, {message.from_user.first_name}!\nВыберите действие:",
        reply_markup=start_menu_keyboard()
    )

async def main_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=start_menu_keyboard())

async def cmd_balance(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(f"Ваш текущий баланс: {user.balance} руб. Одна генерация стоит 150 руб.", reply_markup=balance_keyboard())

@router.callback_query(F.data == "back_to_menu")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.answer("Вы вернулись в главное меню", reply_markup=start_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "topup")
async def handle_topup(callback: CallbackQuery):
    await callback.message.answer("Пополните баланс любым удобным способом:", reply_markup=payment_keyboard())
    await callback.answer()

async def generate_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Генерация изображения", callback_data="generate_images")],
        [InlineKeyboardButton(text="Генерация видео", callback_data="generate_videos")],
        [InlineKeyboardButton(text="Генерация 3D", callback_data="generate_3d")],
        [InlineKeyboardButton(text="Генерация аудио", callback_data="generate_audio")],
    ])
    await message.answer("Выберите тип генерации:", reply_markup=kb)

async def check_balance_and_proceed(callback: CallbackQuery, state: FSMContext, keyboard: InlineKeyboardMarkup, message_text: str):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    if user.balance < PRICE_PER_GENERATION and not ALLOW_GENERATION_WHEN_ZERO:
        await callback.message.answer(f"{NO_GENERATION_MESSAGE}\n\nДля пополнения нажмите:", reply_markup=balance_keyboard())
    else:
        await callback.message.edit_text(message_text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "generate_images")
async def image_models_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Flux (img)", callback_data="img_model_1")],
        [InlineKeyboardButton(text="Flux Pro", callback_data="img_model_2")]
    ])
    await check_balance_and_proceed(callback, state, kb, "Выберите модель генерации изображений:")

@router.callback_query(F.data == "generate_videos")
async def video_models_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Kling", callback_data="vid_model_1")],
        [InlineKeyboardButton(text="Veo 3", callback_data="vid_model_2")]
    ])
    await check_balance_and_proceed(callback, state, kb, "Выберите модель генерации видео:")

@router.callback_query(F.data == "generate_3d")
async def gen_3d_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3D A", callback_data="3d_model_1")],
        [InlineKeyboardButton(text="3D B", callback_data="3d_model_2")]
    ])
    await check_balance_and_proceed(callback, state, kb, "Выберите модель генерации 3D:")

@router.callback_query(F.data == "generate_audio")
async def gen_audio_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Audio A", callback_data="audio_model_1")],
        [InlineKeyboardButton(text="Audio B", callback_data="audio_model_2")]
    ])
    await check_balance_and_proceed(callback, state, kb, "Выберите модель генерации аудио:")



async def process_generation_params(message: Message, state: FSMContext):
    state_data = await state.get_data()
    current_state = await state.get_state()
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    if not current_state or "model" not in state_data:
        await message.answer("Пожалуйста, выберите модель генерации из меню.")
        return

    if user.balance < PRICE_PER_GENERATION and not ALLOW_GENERATION_WHEN_ZERO:
        await message.answer(f"{NO_GENERATION_MESSAGE}\n\nДля пополнения нажмите:", reply_markup=balance_keyboard())
        await state.clear()
        return

    db = SessionLocal()
    user_db = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if user_db.balance >= PRICE_PER_GENERATION:
        user_db.balance -= PRICE_PER_GENERATION
        db.commit()
    else:
        await message.answer(f"{NO_GENERATION_MESSAGE}\n\nДля пополнения нажмите:", reply_markup=balance_keyboard())
        await state.clear()
        db.close()
        return
    db.close()

    model_name = state_data["model"]
    prompt = message.text

    await message.answer("Генерация запущена, подождите результат...")

    # Здесь должна быть логика генерации — заглушка:
    result = f"Заглушка генерации для {model_name} по описанию: {prompt}"
    await message.answer(result)
    await state.clear()

@router.message(GenerationStates.waiting_for_image_params)
@router.message(GenerationStates.waiting_for_video_params)
@router.message(GenerationStates.waiting_for_audio_params)
@router.message(GenerationStates.waiting_for_3d_params)
async def handle_generation_message(message: Message, state: FSMContext):
    await process_generation_params(message, state)

@router.message(F.text == "🎨 Генерация")
async def on_generate_command(message: Message):
    await generate_menu(message)

@router.message(F.text == "📊 Баланс")
async def on_balance_command(message: Message):
    await cmd_balance(message)

@router.callback_query()
async def fallback_callback(callback: CallbackQuery):
    print(f"⚠️ Необработанный callback: {callback.data}")
    await callback.answer()

@router.message()
async def fallback_message(message: Message):
    print(f"⚠️ Необработанное сообщение: {message.text}")

def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command(commands=["start"]))
    dp.message.register(on_generate_command, F.text == "🎨 Генерация")
    dp.message.register(on_balance_command, F.text == "📊 Баланс")
    dp.message.register(main_menu, F.text == "Главное меню")
    if not hasattr(dp, "_router_included"):
        dp.include_router(router)
        dp._router_included = True

async def main():
    print("Запуск бота...")
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден")
        return
    bot = Bot(token=BOT_TOKEN)
    register_handlers(dp)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def main():
    init_db()
    print("База и таблицы готовы")
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден")
        return
    bot = Bot(token=BOT_TOKEN)
    register_handlers(dp)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())