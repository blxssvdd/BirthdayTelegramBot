from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from .states import RegisterState, SettingsState
from .keyboards import get_confirm_birthday_kb, get_timezone_share_kb, get_main_menu_kb
import re
from datetime import datetime, date
import requests
from timezonefinder import TimezoneFinder
import pytz
import logging
from aiogram import F
from bot.calendar import get_years_kb, get_months_kb, get_days_kb, get_confirm_kb

from sqlalchemy import select
from bot.db.database import get_db
from bot.db.users.models import User

router = Router()
logger = logging.getLogger(__name__)

def get_confirm_timezone_kb(tz):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Подтвердить', callback_data=f'confirm_timezone:{tz}'),
             InlineKeyboardButton(text='Изменить', callback_data='change_timezone')]
        ]
    )

@router.message(Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        '🎉 Привет! Я помогу тебе отслеживать, сколько осталось до твоего дня рождения.\n'
        'Пожалуйста, выберите год своего рождения:',
        reply_markup=get_years_kb(2000)
    )
    await state.set_state(RegisterState.waiting_for_birthday)

@router.message(RegisterState.waiting_for_birthday)
async def process_birthday(message: Message, state: FSMContext):
    date_text = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_text):
        await message.answer('❗ Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 16.10.2008)')
        return
    try:
        birthday = datetime.strptime(date_text, '%d.%m.%Y').date()
    except ValueError:
        await message.answer('❗ Некорректная дата. Попробуйте ещё раз.')
        return
    await state.update_data(birthday=birthday.isoformat())
    await message.answer(
        f'📅 Ваша дата рождения: <b>{birthday.strftime("%d.%m.%Y")}</b>\nВсё верно?',
        reply_markup=get_confirm_birthday_kb(),
        parse_mode='HTML'
    )
    await state.set_state(RegisterState.confirm_birthday)

@router.callback_query(lambda c: c.data == 'change_birthday', RegisterState.confirm_birthday)
async def change_birthday(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text('Пожалуйста, отправьте новую дату рождения в формате ДД.ММ.ГГГГ.')
    await state.set_state(RegisterState.waiting_for_birthday)

@router.callback_query(lambda c: c.data == 'confirm_birthday', RegisterState.confirm_birthday)
async def confirm_birthday(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    birthday_iso = user_data.get('birthday')
    try:
        if birthday_iso:
            birth_date = datetime.fromisoformat(birthday_iso).date()
        else:
            birth_date = None
    except Exception:
        birth_date = None

    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == callback_query.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.birthday = birth_date
        else:
            user = User(user_id=callback_query.from_user.id, birthday=birth_date)
            session.add(user)
        await session.commit()

    await callback_query.message.answer(
        'Теперь отправьте ваш город или поделитесь геолокацией для определения часового пояса.',
        reply_markup=get_timezone_share_kb()
    )
    await state.set_state(RegisterState.waiting_for_timezone)
    logger.info(f'FSM: ожидание часового пояса, user_id={callback_query.from_user.id}')
    await callback_query.answer()

@router.message(RegisterState.waiting_for_timezone)
async def process_timezone(message: Message, state: FSMContext):
    try:
        logger.info(f'FSM: ожидание часового пояса, user_id={message.from_user.id}')
        logger.info(f'Получено сообщение: text={message.text}, location={message.location}')
        tz = None
        city = message.text.strip() if message.text else None
        location = message.location
        tf = TimezoneFinder()
        logger.info(f'city={city}, location={location}')
        if location:
            tz = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            logger.info(f'timezonefinder по геолокации: {tz}')
        elif city:
            url = f'https://nominatim.openstreetmap.org/search?city={city}&format=json&limit=1'
            resp = requests.get(url, headers={'User-Agent': 'BirthdayBot'})
            data = resp.json()
            logger.info(f'Nominatim response: {data}')
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                logger.info(f'Координаты города: lat={lat}, lon={lon}')
                tz = tf.timezone_at(lng=lon, lat=lat)
                logger.info(f'timezonefinder по координатам: {tz}')
        logger.info(f'city={city}, location={location}, tz={tz}')
        if not tz:
            logger.warning(f'Не удалось определить часовой пояс для города: {city}, location: {location}')
            await message.answer('❗ Не удалось определить часовой пояс. Попробуйте отправить геолокацию или другой город.')
            return
        async for session in get_db():
            result = await session.execute(select(User).where(User.user_id == message.from_user.id))
            user = result.scalar_one_or_none()
            if user:
                user.timezone = tz
            else:
                user = User(user_id=message.from_user.id, timezone=tz)
                session.add(user)
            await session.commit()

        await message.answer(f'🌍 Ваш часовой пояс: <b>{tz}</b>\nРегистрация завершена! 🎉', parse_mode='HTML')
        await message.answer('Меню', reply_markup=get_main_menu_kb())
        await state.clear()
        logger.info(f'FSM: регистрация завершена, user_id={message.from_user.id}')
    except Exception as e:
        logger.error(f'Ошибка при определении часового пояса: {e}', exc_info=True)
        await message.answer('❗ Произошла ошибка при определении часового пояса. Попробуйте ещё раз или отправьте геолокацию.')

@router.message(SettingsState.waiting_for_new_timezone)
async def set_new_timezone(message: Message, state: FSMContext):
    tz = None
    city = message.text.strip() if message.text else None
    location = message.location
    tf = TimezoneFinder()
    if location:
        tz = tf.timezone_at(lng=location.longitude, lat=location.latitude)
    elif city:
        url = f'https://nominatim.openstreetmap.org/search?city={city}&format=json&limit=1'
        resp = requests.get(url, headers={'User-Agent': 'BirthdayBot'})
        data = resp.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            tz = tf.timezone_at(lng=lon, lat=lat)
    if not tz:
        await message.answer('❗ Не удалось определить часовой пояс. Попробуйте отправить геолокацию или другой город.')
        return
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = tz
        else:
            user = User(user_id=message.from_user.id, timezone=tz)
            session.add(user)
        await session.commit()

    await message.answer(f'🌍 Ваш часовой пояс обновлён: <b>{tz}</b>', parse_mode='HTML')
    await message.answer('Меню', reply_markup=get_main_menu_kb())
    await state.clear()

# Основные команды меню
@router.message(lambda m: m.text and m.text.strip().lower() == 'сколько дней до дня рождения?')
async def days_until_birthday(message: Message):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user or not user.birthday or not user.timezone:
            await message.answer('Сначала завершите регистрацию!')
            return

        birthday = user.birthday
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz).date()
        next_birthday = birthday.replace(year=now.year)
        if next_birthday < now:
            next_birthday = next_birthday.replace(year=now.year + 1)
        days = (next_birthday - now).days
        await message.answer(f'🎂 До вашего дня рождения осталось <b>{days}</b> дней!', parse_mode='HTML')

@router.message(lambda m: m.text and m.text.strip().lower() == 'сколько дней со дня рождения?')
async def days_since_birthday(message: Message):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user or not user.birthday or not user.timezone:
            await message.answer('Сначала завершите регистрацию!')
            return

        birthday = user.birthday
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz).date()
        last_birthday = birthday.replace(year=now.year)
        if last_birthday > now:
            last_birthday = last_birthday.replace(year=now.year - 1)
        days = (now - last_birthday).days
        await message.answer(f'📅 С вашего дня рождения прошло <b>{days}</b> дней!', parse_mode='HTML')

@router.message(lambda m: m.text and m.text.strip().lower() == 'изменить дату')
async def change_birthday_menu(message: Message, state: FSMContext):
    await message.answer('Выберите год своего рождения:', reply_markup=get_years_kb(2000))
    await state.set_state(SettingsState.waiting_for_new_birthday)

@router.message(SettingsState.waiting_for_new_birthday)
async def set_new_birthday(message: Message, state: FSMContext):
    date_text = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_text):
        await message.answer('❗ Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 16.10.2008)')
        return
    try:
        birthday = datetime.strptime(date_text, '%d.%m.%Y').date()
    except ValueError:
        await message.answer('❗ Некорректная дата. Попробуйте ещё раз.')
        return
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.birthday = birthday
        else:
            user = User(user_id=message.from_user.id, birthday=birthday)
            session.add(user)
        await session.commit()

    await message.answer('Дата рождения обновлена!')
    await state.clear()

@router.message(lambda m: m.text and m.text.strip().lower() == 'изменить часовой пояс')
async def change_timezone_menu(message: Message, state: FSMContext):
    await message.answer('Отправьте новый город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(SettingsState.waiting_for_new_timezone)

@router.message(SettingsState.waiting_for_new_timezone)
async def set_new_timezone(message: Message, state: FSMContext):
    tz = None
    city = message.text.strip() if message.text else None
    location = message.location
    tf = TimezoneFinder()
    if location:
        tz = tf.timezone_at(lng=location.longitude, lat=location.latitude)
    elif city:
        url = f'https://nominatim.openstreetmap.org/search?city={city}&format=json&limit=1'
        resp = requests.get(url, headers={'User-Agent': 'BirthdayBot'})
        data = resp.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            tz = tf.timezone_at(lng=lon, lat=lat)
    if not tz:
        await message.answer('❗ Не удалось определить часовой пояс. Попробуйте отправить геолокацию или другой город.')
        return
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = tz
        else:
            user = User(user_id=message.from_user.id, timezone=tz)
            session.add(user)
        await session.commit()

    await message.answer(
        f'🌍 Ваш часовой пояс: <b>{tz}</b>\nВсё верно?',
        parse_mode='HTML',
        reply_markup=get_confirm_timezone_kb(tz)
    )

@router.callback_query(lambda c: c.data.startswith('confirm_timezone:'), SettingsState.waiting_for_new_timezone)
async def confirm_timezone_change_handler(callback: CallbackQuery, state: FSMContext):
    tz = callback.data.split(':', 1)[1]
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = tz
        else:
            user = User(user_id=callback.from_user.id, timezone=tz)
            session.add(user)
        await session.commit()

    await callback.message.edit_text(f'🌍 Ваш часовой пояс обновлён: <b>{tz}</b>', parse_mode='HTML')
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == 'change_timezone', SettingsState.waiting_for_new_timezone)
async def change_timezone_change_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text('Пожалуйста, отправьте новый город или поделитесь геолокацией для определения часового пояса.')
    await callback.message.answer('Отправьте новый город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(SettingsState.waiting_for_new_timezone)
    await callback.answer()

@router.message(lambda m: m.text and m.text.strip().lower() == 'отключить уведомления')
async def disable_notifications(message: Message):
    await message.answer('🔕 Уведомления пока не реализованы, но скоро появятся!')

@router.message(Command('state'))
async def show_state(message: Message, state: FSMContext):
    s = await state.get_state()
    await message.answer(f'Текущее состояние: {s}')

@router.message(Command('menu'))
async def show_main_menu(message: Message, state: FSMContext):
    await message.answer('Доступные команды:\n/menu — главное меню\n/timezone — изменить часовой пояс\n/start — начать регистрацию')

@router.message(Command('timezone'))
async def change_timezone_command(message: Message, state: FSMContext):
    await message.answer('Отправьте новый город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(SettingsState.waiting_for_new_timezone)


@router.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    s = await state.get_state()
    await message.answer(
        "Я не понял команду.\n"
        "Если вы только начали — используйте /start и следуйте инструкции.\n"
        "Если что-то не работает — попробуйте пройти регистрацию заново или напишите /start."
        f"\nТекущее состояние: {s}"
    )

# --- Календарь для выбора даты рождения ---

@router.callback_query(lambda c: c.data.startswith('cal:year:'), RegisterState.waiting_for_birthday)
@router.callback_query(lambda c: c.data.startswith('cal:year:'), SettingsState.waiting_for_new_birthday)
async def calendar_year_handler(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(':')[2])
    await state.update_data(year=year)
    await callback.message.edit_text(
        f'Выберите месяц',
        reply_markup=get_months_kb(year)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:month:'), RegisterState.waiting_for_birthday)
@router.callback_query(lambda c: c.data.startswith('cal:month:'), SettingsState.waiting_for_new_birthday)
async def calendar_month_handler(callback: CallbackQuery, state: FSMContext):
    _, _, year, month = callback.data.split(':')
    year = int(year)
    month = int(month)
    await state.update_data(month=month)
    await callback.message.edit_text(
        f'Выберите день',
        reply_markup=get_days_kb(year, month)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:day:'), RegisterState.waiting_for_birthday)
@router.callback_query(lambda c: c.data.startswith('cal:day:'), SettingsState.waiting_for_new_birthday)
async def calendar_day_handler(callback: CallbackQuery, state: FSMContext):
    _, _, year, month, day = callback.data.split(':')
    year = int(year)
    month = int(month)
    day = int(day)
    date_str = f'{day:02d}.{month:02d}.{year}'
    await state.update_data(day=day, birthday=date_str)
    await callback.message.edit_text(
        f'Выбрана дата {date_str}',
        reply_markup=get_confirm_kb(date_str)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:confirm:'), RegisterState.waiting_for_birthday)
@router.callback_query(lambda c: c.data.startswith('cal:confirm:'), RegisterState.confirm_birthday)
@router.callback_query(lambda c: c.data.startswith('cal:confirm:'), SettingsState.waiting_for_new_birthday)
async def calendar_confirm_handler(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(':')[2]
    iso_date = datetime.strptime(date_str, '%d.%m.%Y').date()
    current_state = await state.get_state()
    if current_state == SettingsState.waiting_for_new_birthday.state:
        async for session in get_db():
            result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
            user = result.scalar_one_or_none()
            if user:
                user.birthday = iso_date
            else:
                user = User(user_id=callback.from_user.id, birthday=iso_date)
                session.add(user)
            await session.commit()
        await callback.message.edit_text('Дата рождения обновлена!')
        await state.clear()
    else:
        await state.update_data(birthday=iso_date.isoformat())
        async for session in get_db():
            result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
            user = result.scalar_one_or_none()
            if user:
                user.birthday = iso_date
            else:
                user = User(user_id=callback.from_user.id, birthday=iso_date)
                session.add(user)
            await session.commit()
        await callback.message.edit_text(
            'Теперь отправьте ваш город или поделитесь геолокацией для определения часового пояса.'
        )
        await callback.message.answer('Отправьте город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
        await state.set_state(RegisterState.waiting_for_timezone)
    await callback.answer()

@router.callback_query(lambda c: c.data == 'cal:change', RegisterState.confirm_birthday)
@router.callback_query(lambda c: c.data == 'cal:change', SettingsState.waiting_for_new_birthday)
async def calendar_change_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(2000))
    if await state.get_state() == RegisterState.confirm_birthday.state:
        await state.set_state(RegisterState.waiting_for_birthday)
    else:
        await state.set_state(SettingsState.waiting_for_new_birthday)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:year_prev:'))
async def calendar_year_prev(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(':')[2])
    new_page = max(0, page - 1)
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(new_page))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:year_next:'))
async def calendar_year_next(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(':')[2])
    new_page = page + 1
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(new_page))
    await callback.answer()

@router.callback_query(lambda c: c.data == 'cal:back_to_years')
async def calendar_back_to_years(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    year = data.get('year')
    from bot.calendar import START_YEAR, YEARS_PER_PAGE
    if year:
        page = (int(year) - START_YEAR) // YEARS_PER_PAGE
    else:
        page = 0
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(page))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith('cal:back_to_months:'))
async def calendar_back_to_months(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(':')[2])
    await callback.message.edit_text('Выберите месяц', reply_markup=get_months_kb(year))
    await callback.answer()
