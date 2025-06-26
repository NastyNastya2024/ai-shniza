import asyncio
import logging
import time
import functools

import replicate
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- КОНФИГ ---
BOT_TOKEN = "7823312563:AAFvO-kLLthRuYrA_uLbKLtWWovOwtxoKb8"
REPLICATE_API_TOKEN = "r8_3EvZNCymOU16GPbngcLGzlvpVDxfkfi2bahdy"

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("tg_bot")

# --- FSM ---
class ImageGenState(StatesGroup):
    AWAITING_PROMPT = State()

# --- Replicate параметры ---
IMAGEN4_VERSION = "4f11bc3c20cd8b49a63ff5fdf3f8c8c66a2642a0a385d3050b79e1c4c189ef19"
IMAGEN4_PARAMS = {
    "aspect_ratio": "16:9",
    "output_format": "png",
    "safety_filter_level": "block_medium_and_above",
    "guidance_scale": 7.5,
    "num_inference_steps": 50
}

# --- Функция генерации через replicate ---
def sync_generate(prompt: str) -> str:
    logger.debug(f"[sync_generate] Старт генерации для промпта: {prompt}")
    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        prediction = client.predictions.create(
            version=IMAGEN4_VERSION,
            input={"prompt": prompt, **IMAGEN4_PARAMS}
        )
        logger.info(f"[sync_generate] Запущена задача генерации, ID: {prediction.id}")

        while not prediction.completed:
            logger.debug(f"[sync_generate] Статус генерации: {prediction.status}")
            time.sleep(3)
            prediction.reload()
            if prediction.status == "failed":
                logger.error("[sync_generate] Генерация завершилась с ошибкой")
                raise RuntimeError("Генерация завершилась с ошибкой")

        if not prediction.output or not isinstance(prediction.output, list):
            logger.error(f"[sync_generate] Некорректный ответ API: {prediction.output}")
            raise ValueError("Пустой или некорректный ответ от API")

        image_url = prediction.output[0]
        logger.info(f"[sync_generate] Генерация завершена. URL: {image_url}")
        return image_url

    except Exception as e:
        logger.exception(f"[sync_generate] Ошибка генерации: {e}")
        raise

# --- Хендлеры ---

async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"[cmd_start] Пользователь {user_id} вызвал /start")
    await message.answer(
        "Привет! Отправь описание (промпт) на английском для генерации изображения.\n"
        "Минимум 15 символов.\n\nПример:\nA fantasy castle on a floating island at sunset"
    )
    await state.set_state(ImageGenState.AWAITING_PROMPT)
    logger.debug(f"[cmd_start] FSM состояние AWAITING_PROMPT установлено для пользователя {user_id}")

async def handle_prompt(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prompt = message.text.strip()
    logger.info(f"[handle_prompt] Пользователь {user_id} отправил промпт: '{prompt}'")

    if len(prompt) < 15:
        logger.warning(f"[handle_prompt] Промпт слишком короткий от пользователя {user_id}")
        await message.answer("❌ Описание должно содержать минимум 15 символов. Попробуйте ещё раз.")
        return

    await message.answer("⏳ Генерирую изображение, это может занять некоторое время...")

    try:
        loop = asyncio.get_event_loop()
        image_url = await loop.run_in_executor(None, functools.partial(sync_generate, prompt))
        logger.info(f"[handle_prompt] Изображение сгенерировано для пользователя {user_id}")

        await message.answer_photo(
            image_url,
            caption=f"✅ Вот ваше изображение по запросу:\n{prompt}"
        )
    except Exception:
        logger.exception(f"[handle_prompt] Ошибка генерации изображения для пользователя {user_id}")
        await message.answer("❌ Ошибка при генерации изображения. Попробуйте позже.")

    await state.clear()
    logger.debug(f"[handle_prompt] FSM состояние очищено для пользователя {user_id}")

# --- Запуск бота ---
async def main():
    logger.info("Запуск Telegram бота...")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация хендлеров
    dp.message.register(cmd_start, F.command("start"))
    dp.message.register(handle_prompt, ImageGenState.AWAITING_PROMPT)

    logger.info("Хендлеры зарегистрированы, стартуем polling.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
