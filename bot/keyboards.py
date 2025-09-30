from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_confirm_birthday_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Подтвердить', callback_data='confirm_birthday')],
        [InlineKeyboardButton(text='✏️ Изменить', callback_data='change_birthday')]
    ])

def get_timezone_share_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📬 Поделиться часовым поясом', request_location=True)]],
        resize_keyboard=True
    )

def get_main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Сколько дней до дня рождения?')],
            [KeyboardButton(text='Сколько дней со дня рождения?')],
            [KeyboardButton(text='Изменить дату')],
            [KeyboardButton(text='Отключить уведомления')]
        ],
        resize_keyboard=True
    ) 