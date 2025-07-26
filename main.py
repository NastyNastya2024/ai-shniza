import os
import logging
import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from models.gpt import PromptTranslationState, gpt_start, handle_russian_prompt
from bot.start import show_payment_options, router as start_router
from models.kling import KlingVideoState, cmd_start_kling, handle_image_kling, handle_mode_selection_kling, handle_duration_selection_kling, handle_prompt_kling, handle_confirm_generation_kling
from models import ideogram, imagegen4, flux, veo3, kling, minimax, seedance, musicgen, chatterbox, gpt
from models.minimax import VideoGenState, minimax_start, minimax_handle_image, minimax_handle_prompt,  minimax_confirm_generation
from models.veo3 import (
    Veo3State,
    cmd_start_veo3,
    handle_prompt_veo3,
    confirm_generation_veo3,
)


from models.imagegen4 import (
    ImageGenState,
    cmd_start_imagegen4,
    aspect_imagegen4,
    handle_prompt_imagegen4,
    confirm_generation_imagegen4,
    go_main_menu_imagegen4,
)

from models.musicgen import (
    MusicGenStates,
    start_handler_musicgen,
    model_chosen_musicgen,
    normalization_chosen_musicgen,
    receive_prompt_musicgen,
    confirm_generation_musicgen,
)

from models.ideogram import (
    IdeogramImageGenState,
    ideogram_start,
    handle_aspect_ideogram,
    handle_style_aspect_ideogram,
    handle_prompt_aspect_ideogram,
    confirm_generation_ideogram,
)



from models.flux import (
    FluxKontextState,
    cmd_start_flux,
    handle_image_flux,
    handle_aspect_ratio_flux,
    handle_flux_style_flux,
    handle_prompt_flux,
    confirm_generation_flux,
    go_main_menu,
)


from models.seedance import (
    SeedanceState,
    seedance_cmd_start,
    seedance_handle_image,
    seedance_handle_prompt,
    seedance_handle_resolution,
    seedance_handle_duration,
    seedance_handle_aspect_ratio,
    seedance_handle_camera_fixed,
    seedance_handle_confirm_generation
)
from models.chatterbox import (
    VoiceGenState,
    go_main_menu_chatterbox,
    cmd_start_chatterbox,
    choose_temperature_chatterbox,
    choose_seed_chatterbox,
    handle_voice_text_chatterbox,
    confirm_generation_chatterbox,
)



from keyboards import (
    MAIN_MENU_BUTTON_TEXT,
    main_menu_kb,
    generation_kb,
    image_menu_kb,
    image_text_menu_kb,
    video_menu_kb,
    video_image_menu_kb,
    music_menu_kb
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
    

async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("❌ Переменные окружения не заданы")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    


# === Основной роутер ===
router = Router()

# === Основные хендлеры ===
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} начал работу")

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Добро пожаловать в бота *AIшница* 🤖\n\n"
        f"_Бот предоставляет платные генерации изображений, видео, аудио и текстов с помощью ИИ._\n\n"

        f"🖼 *Генерация изображений:*\n"
        f"- Ideogram — от 9 ₽\n"
        f"- Imagen-4 — от 9 ₽\n"
        f"- FluxKontext — от 9 ₽\n\n"

        f"🎬 *Генерация видео:*\n"
        f"- Kling v2.1 — от 55 - 199 ₽\n"
        f"- Minimax Video — от 150 ₽\n"
        f"- Seedance  — от 80 ₽\n"
        f"- Veo3 (8 секунд) —  660 ₽\n\n"

        f"🎵 *Генерация музыки:*\n"
        f"- Minimax Music — от 9 ₽\n"
        f"- MusicGen — 9 ₽\n"
        f"- Chatterbox — 9 ₽\n\n"

        f"💬 *Текст и речь:*\n"
        f"- GPT перевод — бесплатно\n\n"

        f"💼 *Юридическая информация:*\n"
        f"ИП А А Комарова\n"
        f"ИНН 504231947047 | \n ОГРН 322508100272216\n\n"
        f"❗ Ознакомьтесь с тарифами и офертой через кнопку 📊 *Баланс*",
        parse_mode="Markdown"
    )

    # 👇 добавлено: сразу переход в главное меню
    await go_main_menu(message, state) 

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Вы в главном меню", reply_markup=main_menu_kb())

@router.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery, state: FSMContext):
    await show_payment_options(callback.message)

@router.callback_query(F.data == "generate")
async def cb_generate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.generation)
    await callback.message.edit_text("Что вы хотите сгенерировать?", reply_markup=generation_kb())

@router.callback_query(F.data == "image_menu")
async def cb_image_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.image_menu)
    await callback.message.edit_text("Выберите тип генерации картинки:", reply_markup=image_menu_kb())

@router.callback_query(F.data == "image_from_text")
async def cb_image_from_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.image_text_menu)
    await callback.message.edit_text("Выберите модель:", reply_markup=image_text_menu_kb())

@router.callback_query(F.data == "image_from_image")
async def cb_image_from_image(callback: CallbackQuery, state: FSMContext):
    await cmd_start_flux(callback.message, state)

@router.callback_query(F.data == "ideogram")
async def cb_ideogram(callback: CallbackQuery, state: FSMContext):
    await ideogram_start(callback.message, state)

@router.callback_query(F.data == "imagegen4")
async def cb_imagegen4(callback: CallbackQuery, state: FSMContext):
    await cmd_start_imagegen4(callback.message, state)

@router.callback_query(F.data == "video_menu")
async def cb_video_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.video_menu)
    await callback.message.edit_text("Выберите тип видео:", reply_markup=video_menu_kb())

@router.callback_query(F.data == "video_from_text")
async def cb_video_from_text(callback: CallbackQuery, state: FSMContext):
    await cmd_start_veo3(callback.message, state)

@router.callback_query(F.data == "video_from_image")
async def cb_video_from_image(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.video_image_menu)
    await callback.message.edit_text("Выберите модель:", reply_markup=video_image_menu_kb())

@router.callback_query(F.data == "kling")
async def cb_kling(callback: CallbackQuery, state: FSMContext):
    await cmd_start_kling(callback.message, state)

@router.callback_query(F.data == "minimax")
async def cb_minimax(callback: CallbackQuery, state: FSMContext):
    await minimax_start(callback.message, state)

@router.callback_query(F.data == "seedance")
async def cb_seedance(callback: CallbackQuery, state: FSMContext):
    await seedance_cmd_start(callback.message, state)

@router.callback_query(F.data == "music_menu")
async def cb_music_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuState.music_menu)
    await callback.message.edit_text("Выберите модель:", reply_markup=music_menu_kb())

@router.callback_query(F.data == "musicgen")
async def cb_musicgen(callback: CallbackQuery, state: FSMContext):
    await start_handler_musicgen(callback.message, state)

@router.callback_query(F.data == "chatterbox")
async def cb_chatterbox(callback: CallbackQuery, state: FSMContext):
    await cmd_start_chatterbox(callback.message, state)

@router.callback_query(F.data == "translate")
async def cb_translate(callback: CallbackQuery, state: FSMContext):
    await gpt_start(callback.message, state)



# === Запуск ===
async def main():
    if not BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("❌ Переменные окружения не заданы")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(router)
    dp.include_router(start_router) # подключение кнопок оплаты

    # === Регистрация FSM-хендлеров ===

    dp.message.register(go_main_menu, Command("main"))
    dp.message.register(go_main_menu, F.text.lower() == "main")
    
    # ImageGen4 (Google Imagen)
    dp.message.register(cmd_start_imagegen4, F.text == "Imagegen4.py")
    dp.callback_query.register(aspect_imagegen4, F.data.startswith("aspect_"), StateFilter(ImageGenState.AWAITING_ASPECT))
    dp.message.register(handle_prompt_imagegen4, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.message.register(go_main_menu_imagegen4, F.text == MAIN_MENU_BUTTON_TEXT, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.callback_query.register(confirm_generation_imagegen4, F.data == "confirm_generation_imagegen4", StateFilter(ImageGenState.CONFIRM_GENERATION))

    
    dp.message.register(gpt_start, F.text == "🔤 Перевод")
    dp.message.register(handle_russian_prompt, StateFilter(PromptTranslationState.WAITING_RU_PROMPT))

    dp.message.register(go_main_menu_chatterbox, F.text == MAIN_MENU_BUTTON_TEXT, StateFilter("*"))
    dp.message.register(cmd_start_chatterbox, F.text == "Chatterbox")
    dp.callback_query.register(choose_temperature_chatterbox, F.data.startswith("temp_"), StateFilter(VoiceGenState.CHOOSE_TEMPERATURE))
    dp.callback_query.register(choose_seed_chatterbox, F.data.startswith("seed_"), StateFilter(VoiceGenState.CHOOSE_SEED))
    dp.message.register(handle_voice_text_chatterbox, StateFilter(VoiceGenState.AWAITING_TEXT))
    dp.callback_query.register(confirm_generation_chatterbox, F.data == "confirm_generation", StateFilter(VoiceGenState.CONFIRM_GENERATION))

    dp.message.register(minimax_start, F.text == "Minimax")
    dp.message.register(minimax_handle_image, StateFilter(VideoGenState.waiting_image))
    dp.message.register(minimax_handle_prompt, StateFilter(VideoGenState.waiting_prompt))
    dp.callback_query.register(minimax_confirm_generation, F.data == "confirm_generation", StateFilter(VideoGenState.confirming_payment))

    dp.message.register(seedance_handle_image, StateFilter(SeedanceState.waiting_image))
    dp.message.register(seedance_handle_prompt, StateFilter(SeedanceState.waiting_prompt))
    dp.callback_query.register(seedance_handle_resolution, StateFilter(SeedanceState.waiting_resolution), lambda c: c.data.startswith("res_"))
    dp.callback_query.register(seedance_handle_duration, StateFilter(SeedanceState.waiting_duration), lambda c: c.data.startswith("dur_"))
    dp.callback_query.register(seedance_handle_aspect_ratio, StateFilter(SeedanceState.waiting_aspect_ratio), lambda c: c.data.startswith("ar_"))
    dp.callback_query.register(seedance_handle_camera_fixed, StateFilter(SeedanceState.waiting_camera_fixed), lambda c: c.data in ["cam_fixed", "cam_move"])
    dp.callback_query.register(seedance_handle_confirm_generation, lambda c: c.data == "confirm_generation")

    dp.message.register(cmd_start_kling, F.text == "Kling")
    dp.message.register(handle_image_kling, StateFilter(KlingVideoState.waiting_image))
    dp.callback_query.register(handle_mode_selection_kling, F.data.startswith("mode_"), StateFilter(KlingVideoState.waiting_mode))
    dp.callback_query.register(handle_duration_selection_kling, F.data.startswith("duration_"), StateFilter(KlingVideoState.waiting_duration))
    dp.message.register(handle_prompt_kling, StateFilter(KlingVideoState.waiting_prompt))
    dp.callback_query.register(handle_confirm_generation_kling, F.data == "confirm_gen", StateFilter(KlingVideoState.confirm_pending))
    dp.message.register(go_main_menu, F.text == MAIN_MENU_BUTTON_TEXT)

    
    dp.message.register(start_handler_musicgen, F.text == "MusicGen")
    dp.callback_query.register(model_chosen_musicgen, StateFilter(MusicGenStates.choosing_model))
    dp.callback_query.register(normalization_chosen_musicgen, StateFilter(MusicGenStates.choosing_normalization))
    dp.message.register(receive_prompt_musicgen, StateFilter(MusicGenStates.waiting_for_prompt))
    dp.callback_query.register(confirm_generation_musicgen, F.data == "confirm_generation_musicgen", StateFilter(MusicGenStates.confirming_payment))

    dp.message.register(cmd_start_veo3, F.text == "Veo3")
    dp.message.register(handle_prompt_veo3, StateFilter(Veo3State.waiting_for_prompt))
    dp.callback_query.register(confirm_generation_veo3, F.data == "confirm_generation_veo3", StateFilter(Veo3State.confirming_payment))
        
    dp.message.register(cmd_start_imagegen4, F.text == "Imagegen4.py")
    dp.callback_query.register(aspect_imagegen4, F.data.startswith("aspect_"), StateFilter(ImageGenState.AWAITING_ASPECT))
    dp.message.register(handle_prompt_imagegen4, StateFilter(ImageGenState.AWAITING_PROMPT))
    dp.callback_query.register(confirm_generation_imagegen4, F.data == "confirm_generation_imagegen4", StateFilter(ImageGenState.CONFIRM_GENERATION))
    dp.message.register(go_main_menu_imagegen4, F.text == MAIN_MENU_BUTTON_TEXT, StateFilter("*"))

    # === Ideogram ===
    dp.message.register(ideogram_start, F.text == "Ideogram.py")
    dp.callback_query.register(handle_aspect_ideogram, F.data.startswith("ideogram_aspect_"), StateFilter(IdeogramImageGenState.SELECTING_ASPECT))
    dp.callback_query.register(handle_style_aspect_ideogram, F.data.startswith("ideogram_style_"), StateFilter(IdeogramImageGenState.SELECTING_STYLE))
    dp.message.register(handle_prompt_aspect_ideogram, StateFilter(IdeogramImageGenState.AWAITING_PROMPT))
    dp.callback_query.register(confirm_generation_ideogram, F.data == "confirm_generation_ideogram", StateFilter(IdeogramImageGenState.CONFIRM_GENERATION_IDEOGRAM))

    dp.message.register(cmd_start_flux, F.text == "Flux")
    dp.message.register(handle_image_flux, StateFilter(FluxKontextState.WAITING_IMAGE))
    dp.callback_query.register(handle_aspect_ratio_flux, StateFilter(FluxKontextState.WAITING_ASPECT_RATIO))
    dp.message.register(handle_prompt_flux, StateFilter(FluxKontextState.WAITING_PROMPT))
    dp.callback_query.register(confirm_generation_flux, F.data == "confirm_generation_flux", StateFilter(FluxKontextState.CONFIRM_GENERATION_FLUX))
    dp.message.register(go_main_menu, F.text == "🏠 Главное меню")

    logger.info("🤖 Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())