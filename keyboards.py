from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup

def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="EN-US"),
         InlineKeyboardButton(text="🇪🇸 Spanish", callback_data="ES")],
        [InlineKeyboardButton(text="🇫🇷 French", callback_data="FR"),
         InlineKeyboardButton(text="🇩🇪 German", callback_data="DE")],
        [InlineKeyboardButton(text="🇮🇹 Italian", callback_data="IT"),
         InlineKeyboardButton(text="🇵🇹 Portuguese", callback_data="PT")],
        [InlineKeyboardButton(text="🇳🇱 Dutch", callback_data="NL"),
         InlineKeyboardButton(text="🇯🇵 Japanese", callback_data="JA")],
        [InlineKeyboardButton(text="🇹🇷 Turkish", callback_data="TR"),
         InlineKeyboardButton(text="🇨🇳 Chinese", callback_data="ZH")],
        [InlineKeyboardButton(text="🇷🇺 Russian", callback_data="RU")],
    ])
    return keyboard

def main_menu():
    send_file_button = KeyboardButton(text="Отправить файл на перевод")
    keyboard = [[send_file_button]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_approval_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="approve_payment")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")]
    ])
    return keyboard

def get_wallet_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 RUB", callback_data="top_up_wallet_100")],
        [InlineKeyboardButton(text="500 RUB", callback_data="top_up_wallet_500")],
        [InlineKeyboardButton(text="1000 RUB", callback_data="top_up_wallet_1000")]
    ])
    return keyboard
