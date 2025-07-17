from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Универсальный текст кнопки
MAIN_MENU_BUTTON_TEXT = "🏠 Главное меню"

# Универсальная кнопка
main_menu_button = KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)

# Главное меню
def main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎨 Генерация")],
        [KeyboardButton(text="🔤 Перевод")],
        [KeyboardButton(text="📊 Баланс")]
    ], resize_keyboard=True)
    
def imagegen4_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [main_menu_button]
    ], resize_keyboard=True)
     
def gpt_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [main_menu_button]
    ], resize_keyboard=True)
    
# Универсальная клавиатура "Назад"
def universal_back_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [main_menu_button]
    ], resize_keyboard=True)

# Chatterbox меню
def chatterbox_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [main_menu_button]
    ], resize_keyboard=True)

# Остальные меню (если используются)
def generation_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🖼 Картинка"), KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="🎵 Музыка")],
        [main_menu_button]
    ], resize_keyboard=True)

def image_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🖋 Картинка из текста")],
        [KeyboardButton(text="🖼 Картинка из картинки")],
        [main_menu_button]
    ], resize_keyboard=True)

def image_text_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Ideogram.py"), KeyboardButton(text="Imagegen4.py")],
        [main_menu_button]
    ], resize_keyboard=True)

def video_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📄 Видео из текста")],
        [KeyboardButton(text="🖼 Видео из картинки")],
        [main_menu_button]
    ], resize_keyboard=True)

def video_image_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Kling"), KeyboardButton(text="Minimax")],
        [KeyboardButton(text="Seedance")],
        [main_menu_button]
    ], resize_keyboard=True)

def music_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="MusicMax"), KeyboardButton(text="MusicGen")],
        [KeyboardButton(text="Chatterbox")],
        [main_menu_button]
    ], resize_keyboard=True)
    
def kling_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Повторить генерацию")],
        [KeyboardButton(text=MAIN_MENU_BUTTON_TEXT)]
    ], resize_keyboard=True)
    
def ideogram_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔁 Новая генерация")],
        [main_menu_button]
    ], resize_keyboard=True)
