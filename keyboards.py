from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton



# Универсальный текст кнопки
MAIN_MENU_BUTTON_TEXT = "🏠 Главное меню"

# Универсальная кнопка
main_menu_button = KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)

# Главное меню
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Генерация", callback_data="generate")],
        [InlineKeyboardButton(text="🔤 Перевод", callback_data="translate")],
        [InlineKeyboardButton(text="📊 Баланс", callback_data="balance")]
    ])

# Меню "Генерация"
def generation_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Картинка", callback_data="image_menu"),
         InlineKeyboardButton(text="🎬 Видео", callback_data="video_menu")],
        [InlineKeyboardButton(text="🎵 Музыка", callback_data="music_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

# Меню "Картинка"
def image_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖋 Картинка из текста", callback_data="image_from_text")],
        [InlineKeyboardButton(text="🖼 Картинка из картинки", callback_data="image_from_image")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

def image_text_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ideogram.py", callback_data="ideogram")],
        [InlineKeyboardButton(text="Imagegen4.py", callback_data="imagegen4")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

# Меню "Видео"
def video_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Видео из текста", callback_data="video_from_text")],
        [InlineKeyboardButton(text="🖼 Видео из картинки", callback_data="video_from_image")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

def video_image_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Kling", callback_data="kling"),
         InlineKeyboardButton(text="Minimax", callback_data="minimax")],
        [InlineKeyboardButton(text="Seedance", callback_data="seedance")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

# Меню "Музыка"
def music_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="MusicGen", callback_data="musicgen"),
         InlineKeyboardButton(text="Chatterbox", callback_data="chatterbox")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

# Kling submenu (если потребуется)
def kling_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
