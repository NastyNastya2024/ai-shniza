import logging
import fal_client
from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher

logger = logging.getLogger(__name__)

class VideoGenStatesVeo3(StatesGroup):
    waiting_for_prompt = State()
    processing_video = State()
    video_ready = State()

async def start_veo3_generation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("✏️ Введите текстовое описание (prompt) для модели Veo 3 на английском (русский модель может не распознать - для перевода используйте чат gpt):")
    await state.set_state(VideoGenStatesVeo3.waiting_for_prompt)
    logger.info("🟢 FSM Veo3: ожидаем промпт")

async def handle_veo3_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("❌ Введите корректный текст.")
        return
    await state.update_data(prompt=prompt)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Генерировать видео (Veo3)", callback_data="generate_video_veo3")],
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data="check_status_veo3")]
    ])
    await message.answer("📋 Что дальше?", reply_markup=keyboard)
    await state.set_state(VideoGenStatesVeo3.processing_video)
    logger.info("🟢 FSM Veo3: ожидаем действия")

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            logger.info(f"Veo3 in-progress: {log['message']}")

async def generate_video_veo3(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    prompt = data.get("prompt")

    if not prompt:
        await callback.message.answer("❌ Не введён промпт.")
        await state.clear()
        return

    await callback.message.edit_text("⏳ Генерирую видео с Veo 3. Это может занять несколько минут...")

    # Запускаем fal_client.subscribe в отдельном потоке, чтобы не блокировать
    import asyncio
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: fal_client.subscribe(
            "fal-ai/veo3",
            arguments={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "duration": "8s",
                "enhance_prompt": True,
                "generate_audio": True
            },
            with_logs=True,
            on_queue_update=on_queue_update,
        ))
    except Exception as e:
        logger.error(f"Ошибка Veo3: {e}")
        await callback.message.answer("❌ Ошибка генерации видео Veo3.")
        await state.clear()
        return

    video_url = None
    # В разных ответах может быть структура, ищем видео
    if isinstance(result, dict):
        video_url = (
            result.get("video_url") or
            (result.get("video") and result["video"].get("url")) or
            (result.get("output") and result["output"].get("video"))
        )

    if video_url:
        await callback.message.answer_video(video_url, caption="🎉 Видео Veo3 готово!")
        await state.update_data(video_url=video_url)
        await state.set_state(VideoGenStatesVeo3.video_ready)
    else:
        await callback.message.answer("❌ Не удалось получить ссылку на видео Veo3.")
        await state.clear()

async def check_status_veo3(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    video_url = data.get("video_url")
    if video_url:
        await callback.message.answer_video(video_url, caption="✅ Видео Veo3 готово.")
    else:
        await callback.message.answer("⏳ Видео Veo3 ещё не готово.")

def setup_veo3_handlers(dp: Dispatcher):
    dp.callback_query.register(start_veo3_generation, F.data == "vid_model_2")
    dp.message.register(handle_veo3_prompt, VideoGenStatesVeo3.waiting_for_prompt, F.text)
    dp.callback_query.register(generate_video_veo3, F.data == "generate_video_veo3", VideoGenStatesVeo3.processing_video)
    dp.callback_query.register(check_status_veo3, F.data == "check_status_veo3", VideoGenStatesVeo3.processing_video)

