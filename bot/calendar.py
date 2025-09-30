from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
import calendar

YEARS_PER_PAGE = 5 * 4
START_YEAR = 1950
END_YEAR = datetime.now().year + 1

MONTHS = [
    'январь', 'февраль', 'март', 'апрель',
    'май', 'июнь', 'июль', 'август',
    'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
]

def get_years_kb(page: int = 0):
    builder = InlineKeyboardBuilder()
    max_page = (END_YEAR - START_YEAR - 1) // YEARS_PER_PAGE
    page = max(0, min(page, max_page))
    start = START_YEAR + page * YEARS_PER_PAGE
    years = [y for y in range(start, min(start + YEARS_PER_PAGE, END_YEAR))]
    if years:
        for i in range(0, len(years), 5):
            row = [InlineKeyboardButton(text=str(y), callback_data=f"cal:year:{y}:{page}") for y in years[i:i+5]]
            builder.row(*row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='←', callback_data=f'cal:year_prev:{page}'))
    else:
        nav.append(InlineKeyboardButton(text=' ', callback_data='noop'))
    if page < max_page:
        nav.append(InlineKeyboardButton(text='→', callback_data=f'cal:year_next:{page}'))
    else:
        nav.append(InlineKeyboardButton(text=' ', callback_data='noop'))
    builder.row(*nav)
    return builder.as_markup()

def get_months_kb(year: int):
    builder = InlineKeyboardBuilder()
    for i in range(0, 12, 3):
        row = [InlineKeyboardButton(text=MONTHS[j], callback_data=f"cal:month:{year}:{j+1}") for j in range(i, i+3)]
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(text='←', callback_data=f'cal:back_to_years'),
        InlineKeyboardButton(text=str(year), callback_data='cal:back_to_years'),
        InlineKeyboardButton(text=' ', callback_data='noop')
    )
    return builder.as_markup()

def get_days_kb(year: int, month: int):
    builder = InlineKeyboardBuilder()
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days+1))
    for i in range(0, num_days, 7):
        row = [InlineKeyboardButton(text=str(d), callback_data=f"cal:day:{year}:{month}:{d}") for d in days[i:i+7]]
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(text='←', callback_data=f'cal:back_to_months:{year}'),
        InlineKeyboardButton(text=f'{year}, {MONTHS[month-1][:3]}.', callback_data=f'cal:back_to_months:{year}'),
        InlineKeyboardButton(text=' ', callback_data='noop')
    )
    return builder.as_markup()

def get_confirm_kb(date_str: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Подтвердить', callback_data=f'cal:confirm:{date_str}'),
             InlineKeyboardButton(text='Изменить', callback_data='cal:change')]
        ]
    ) 