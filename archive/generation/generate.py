import os
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import Update
from dotenv import load_dotenv

# Импорты генераторов

from generation.models.model_video_1 import start_video_generation, setup_video_handlers
from generation.models.model_video_2 import setup_veo3_handlers
from generation.models.model_video_3 import start_pixverse_generation, setup_pixverse_handlers

from generation.models.model_image_1 import start_image_generation_1, setup_imagegen1_handlers
from generation.models.model_image_2 import setup_imagegen2_handlers
#from generation.models.model_image_3 import start_image_generation_3

#from generation.models.model_3D_1 import start_3d_gen_1, setup_3d_1
#from generation.models.model_3D_2 import start_3d_gen_2, setup_3d_2
#from generation.models.model_3D_3 import start_3d_gen_3, setup_3d_3

#from generation.models.model_audio_1 import start_audio_gen_1, setup_audio_1
#from generation.models.model_audio_2 import start_audio_gen_2, setup_audio_2
#from generation.models.model_audio_3 import start_audio_gen_3, setup_audio_3

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- Регистрация обработчиков
setup_video_handlers(dp)
setup_veo3_handlers(dp)
setup_pixverse_handlers(dp)

setup_imagegen1_handlers(dp)
setup_imagegen2_handlers(dp)

setup_3d_1(dp)
setup_3d_2(dp)
setup_3d_3(dp)

setup_audio_1(dp)
setup_audio_2(dp)
setup_audio_3(dp)

# --- Главное меню
@dp.message(F.text)
async def main_menu(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Генерация картинок", callback_data="generate_images")],
        [InlineKeyboardButton(text="🎬 Генерация видео", callback_data="generate_videos")],
        [InlineKeyboardButton(text="🧊 Генерация 3D", callback_data="generate_3d")],
        [InlineKeyboardButton(text="🎵 Генерация аудио", callback_data="generate_audio")]
    ])
    await message.answer("Выберите действие:", reply_markup=keyboard)

# --- Подменю Видео
@dp.callback_query(F.data == "generate_videos")
async def video_models_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Kling (img + text)", callback_data="vid_model_1")],
        [InlineKeyboardButton(text="Veo 3 (text)", callback_data="vid_model_2")],
        [InlineKeyboardButton(text="Pixverse 4.5 (img + text)", callback_data="vid_model_3")],
    ])
    await callback.message.edit_text("Выберите модель генерации видео:", reply_markup=keyboard)

@dp.callback_query(F.data == "vid_model_1")
async def handle_video_model_1(callback: CallbackQuery, state: FSMContext):
    await start_video_generation(callback, state)

@dp.callback_query(F.data == "vid_model_2")
async def handle_video_model_2(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Veo 3 уже запущен. Введите текст...")

@dp.callback_query(F.data == "vid_model_3")
async def handle_video_model_3(callback: CallbackQuery, state: FSMContext):
    await start_pixverse_generation(callback, state)

# --- Подменю Картинки
@dp.callback_query(F.data == "generate_images")
async def image_models_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Flux (img)", callback_data="img_model_1")],
        [InlineKeyboardButton(text="Flux Pro (img + prompt)", callback_data="img_model_2")],
        [InlineKeyboardButton(text="ImageGen 3 (text, advanced)", callback_data="img_model_3")],
    ])
    await callback.message.edit_text("Выберите модель генерации изображений:", reply_markup=keyboard)

@dp.callback_query(F.data == "img_model_1")
async def handle_image_model_1(callback: CallbackQuery, state: FSMContext):
    await start_image_generation_1(callback, state)

@dp.callback_query(F.data == "img_model_2")
async def handle_image_model_2(callback: CallbackQuery, state: FSMContext):
    await start_image_generation_2(callback, state)

@dp.callback_query(F.data == "img_model_3")
async def handle_image_model_3(callback: CallbackQuery, state: FSMContext):
    await start_image_generation_3(callback, state)

# --- Подменю 3D
@dp.callback_query(F.data == "generate_3d")
async def gen_3d_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3D Model A", callback_data="3d_model_1")],
        [InlineKeyboardButton(text="3D Model B", callback_data="3d_model_2")],
        [InlineKeyboardButton(text="3D Model C", callback_data="3d_model_3")],
    ])
    await callback.message.edit_text("Выберите модель генерации 3D:", reply_markup=keyboard)

@dp.callback_query(F.data == "3d_model_1")
async def handle_3d_model_1(callback: CallbackQuery, state: FSMContext):
    await start_3d_gen_1(callback, state)

@dp.callback_query(F.data == "3d_model_2")
async def handle_3d_model_2(callback: CallbackQuery, state: FSMContext):
    await start_3d_gen_2(callback, state)

@dp.callback_query(F.data == "3d_model_3")
async def handle_3d_model_3(callback: CallbackQuery, state: FSMContext):
    await start_3d_gen_3(callback, state)

# --- Подменю Аудио
@dp.callback_query(F.data == "generate_audio")
async def gen_audio_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AudioGen A", callback_data="audio_model_1")],
        [InlineKeyboardButton(text="AudioGen B", callback_data="audio_model_2")],
        [InlineKeyboardButton(text="AudioGen C", callback_data="audio_model_3")],
    ])
    await callback.message.edit_text("Выберите модель генерации аудио:", reply_markup=keyboard)

@dp.callback_query(F.data == "audio_model_1")
async def handle_audio_model_1(callback: CallbackQuery, state: FSMContext):
    await start_audio_gen_1(callback, state)

@dp.callback_query(F.data == "audio_model_2")
async def handle_audio_model_2(callback: CallbackQuery, state: FSMContext):
    await start_audio_gen_2(callback, state)

@dp.callback_query(F.data == "audio_model_3")
async def handle_audio_model_3(callback: CallbackQuery, state: FSMContext):
    await start_audio_gen_3(callback, state)

# --- Обработка необработанных событий
@dp.update()
async def catch_unhandled_updates(update: Update):
    print(f"⚠️ НЕОБРАБОТАННОЕ СОБЫТИЕ: {update}")

# --- Старт
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
