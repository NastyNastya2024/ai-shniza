# bot/handlers/generation.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from bot.config import PRICE_PER_GENERATION, ALLOW_GENERATION_WHEN_ZERO, NO_GENERATION_MESSAGE
from database import SessionLocal, User

generation_router = Router()

class GenerationStates(StatesGroup):
    waiting_for_image_params = State()
    waiting_for_video_params = State()
    waiting_for_audio_params = State()
    waiting_for_3d_params = State()

def generation_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Генерация изображения", callback_data="generate_images")],
        [InlineKeyboardButton(text="Генерация видео", callback_data="generate_videos")],
        [InlineKeyboardButton(text="Генерация 3D", callback_data="generate_3d")],
        [InlineKeyboardButton(text="Генерация аудио", callback_data="generate_audio")]
    ])

@generation_router.message(F.text == "🎨 Генерация")
async def generate_menu(message: Message):
    await message.answer("Выберите тип генерации:", reply_markup=generation_type_keyboard())

# Карты для моделей
model_mapping = {
    "generate_images": [
        ("Flux (img)", "img_model_1"),
        ("Flux Pro", "img_model_2"),
        ("Google / imagen-4 (бесплатно)", "img_model_3"),
    ],
    "generate_videos": [
        ("Kling", "vid_model_1"),
        ("Veo 3", "vid_model_2"),
    ],
    "generate_3d": [
        ("3D A", "3d_model_1"),
        ("3D B", "3d_model_2"),
    ],
    "generate_audio": [
        ("Audio A", "audio_model_1"),
        ("Audio B", "audio_model_2"),
    ]
}

model_to_state = {
    "img_model_1": ("flux_img", GenerationStates.waiting_for_image_params),
    "img_model_2": ("flux_pro", GenerationStates.waiting_for_image_params),
    "img_model_3": ("imagen4", GenerationStates.waiting_for_image_params),
    "vid_model_1": ("kling", GenerationStates.waiting_for_video_params),
    "vid_model_2": ("veo3", GenerationStates.waiting_for_video_params),
    "3d_model_1": ("3d_a", GenerationStates.waiting_for_3d_params),
    "3d_model_2": ("3d_b", GenerationStates.waiting_for_3d_params),
    "audio_model_1": ("audio_a", GenerationStates.waiting_for_audio_params),
    "audio_model_2": ("audio_b", GenerationStates.waiting_for_audio_params),
}

def balance_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

async def get_or_create_user(user_id: int, username: str):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        user = User(telegram_id=user_id, username=username, balance=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@generation_router.callback_query(F.data.startswith("generate_"))
async def select_generation_type(callback: CallbackQuery):
    buttons = model_mapping.get(callback.data, [])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=cb)] for label, cb in buttons]
    )
    await callback.message.answer("Выберите модель:", reply_markup=keyboard)
    await callback.answer()

@generation_router.callback_query(F.data.in_(model_to_state.keys()))
async def select_model(callback: CallbackQuery, state: FSMContext):
    model_code, next_state = model_to_state[callback.data]
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username)

    if model_code != "imagen4" and user.balance < PRICE_PER_GENERATION and not ALLOW_GENERATION_WHEN_ZERO:
        await callback.message.answer(NO_GENERATION_MESSAGE, reply_markup=balance_keyboard())
        await callback.answer()
        return

    await state.clear()
    await state.set_state(next_state)
    await state.update_data(model=model_code)
    await callback.message.answer(f"Выбрана модель {model_code}. Введите описание:")
    await callback.answer()

@generation_router.message(
    GenerationStates.waiting_for_image_params,
    GenerationStates.waiting_for_video_params,
    GenerationStates.waiting_for_audio_params,
    GenerationStates.waiting_for_3d_params
)
async def process_generation_input(message: Message, state: FSMContext):
    data = await state.get_data()
    model = data.get("model")
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    if model != "imagen4" and user.balance < PRICE_PER_GENERATION and not ALLOW_GENERATION_WHEN_ZERO:
        await message.answer(NO_GENERATION_MESSAGE, reply_markup=balance_keyboard())
        await state.clear()
        return

    if model != "imagen4":
        db = SessionLocal()
        db_user = db.query(User).filter(User.telegram_id == user.telegram_id).first()
        if db_user.balance >= PRICE_PER_GENERATION:
            db_user.balance -= PRICE_PER_GENERATION
            db.commit()
        db.close()

    await message.answer(f"Генерация запущена для модели {model} по описанию:\n{message.text}\n\n(Заглушка)")
    await state.clear()
