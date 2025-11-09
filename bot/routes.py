from aiogram import types, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
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

from sqlalchemy import select, update
from bot.db.database import get_db
from bot.db.users.models import User

router = Router()
logger = logging.getLogger(__name__)

def get_confirm_timezone_kb(tz, city=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Подтвердить', callback_data=f'confirm_timezone:{tz}'),
             InlineKeyboardButton(text='Изменить', callback_data='change_timezone')]
        ]
    )

def get_disable_notifications_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Да, отключить', callback_data='confirm_disable_notifications')],
            [InlineKeyboardButton(text='❌ Нет, отменить', callback_data='cancel_disable_notifications')]
        ]
    )

def get_timezone_message(city, timezone):
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz).strftime('%H:%M')
    except Exception as e:
        logger.error(f"Ошибка при получении времени для таймзоны {timezone}: {e}")
        current_time = "неизвестно"
    
    message = ""
    if city:
        message += f"📍 Город: {city}\n"
    message += f"🌍 Ваш часовой пояс: {timezone}\n"
    message += f"🕐 Ваше время: {current_time}"
    
    return message

# Команда /menu работает ВСЕГДА
@router.message(Command('menu'))
async def show_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('Главное меню:', reply_markup=get_main_menu_kb())

@router.message(Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        '🎉 Привет! Я помогу тебе отслеживать, сколько осталось до твоего дня рождения.\n'
        'Пожалуйста, выберите год своего рождения:',
        reply_markup=get_years_kb(2000)
    )
    await state.set_state(RegisterState.waiting_for_birthday)

@router.message(Command('help'))
async def cmd_help(message: Message):
        photo = FSInputFile("img/1500x500.jpg")

        text = (
        "🪩 <b>Birthday Counter — помощь</b>\n\n"
        "👋 Привет! Я напомню о твоём дне рождения и помогу посчитать дни.\n\n"
        "<b>Команды и фразы:</b>\n"
        "• <b>/start</b> — начать регистрацию или обновить данные.\n"
        "• <b>/timezone</b> — указать новую дату рождения.\n"
        "• <b>/menu</b> — Выход в главное меню.\n"
        "• <b>Сколько дней до дня рождения?</b> — сколько осталось.\n"
        "• <b>Сколько дней со дня рождения?</b> — сколько прошло.\n"
        "• <b>Изменить дату</b> — изменить дату вашего дня рождения.\n"
        "• <b>Отключить уведомления</b> — удалить данные.\n\n"
        "💡 <i>Подсказка:</i> отправь город или поделись геолокацией — я сам определю часовой пояс.\n"
        "✨ Хорошего дня и приятного ожидания праздника! 😊"
        )

        await message.answer_photo(photo=photo, caption=text, parse_mode='HTML')

@router.message(RegisterState.waiting_for_birthday)
async def process_birthday(message: Message, state: FSMContext):
    date_text = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_text):
        await message.answer('❗ Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 11.11.2000)')
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

@router.callback_query(F.data == 'confirm_birthday', RegisterState.confirm_birthday)
async def confirm_birthday(callback_query: CallbackQuery, state: FSMContext):
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
            user.notifications_enabled = True
        else:
            user = User(user_id=callback_query.from_user.id, birthday=birth_date, notifications_enabled=True)
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
            if not city:
                url = f'https://nominatim.openstreetmap.org/reverse?lat={location.latitude}&lon={location.longitude}&format=json'
                resp = requests.get(url, headers={'User-Agent': 'BirthdayBot'})
                data = resp.json()
                if data and 'address' in data:
                    city = data['address'].get('city') or data['address'].get('town') or data['address'].get('village') or data['address'].get('municipality')
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
        
        await state.update_data(timezone=tz, city=city)
        
        timezone_message = get_timezone_message(city, tz)
        await message.answer(
            timezone_message,
            reply_markup=get_confirm_timezone_kb(tz, city)
        )
        await state.set_state(RegisterState.confirm_timezone)
        logger.info(f'FSM: подтверждение часового пояса, user_id={message.from_user.id}')
        
    except Exception as e:
        logger.error(f'Ошибка при определении часового пояса: {e}', exc_info=True)
        await message.answer('❗ Произошла ошибка при определении часового пояса. Попробуйте ещё раз или отправьте геолокацию.')

@router.callback_query(F.data.startswith('confirm_timezone:'), RegisterState.confirm_timezone)
async def confirm_timezone_handler(callback: CallbackQuery, state: FSMContext):
    tz = callback.data.split(':', 1)[1]
    user_data = await state.get_data()
    city = user_data.get('city')
    
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = tz
            user.city = city
        else:
            user = User(user_id=callback.from_user.id, timezone=tz, city=city, notifications_enabled=True)
            session.add(user)
        await session.commit()

    timezone_message = get_timezone_message(city, tz)
    await callback.message.edit_text(f'{timezone_message}\n\n✅ Регистрация завершена! 🎉')
    await callback.message.answer('Меню', reply_markup=get_main_menu_kb())
    await state.clear()
    logger.info(f'FSM: регистрация завершена, user_id={callback.from_user.id}')
    await callback.answer()

@router.callback_query(F.data == 'change_timezone', RegisterState.confirm_timezone)
async def change_timezone_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text('Пожалуйста, отправьте ваш город или поделитесь геолокацией для определения часового пояса.')
    await callback.message.answer('Отправьте город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(RegisterState.waiting_for_timezone)
    await callback.answer()

# Обработчики для изменения часового пояса в настройках
@router.message(SettingsState.waiting_for_new_timezone)
async def set_new_timezone(message: Message, state: FSMContext):
    try:
        tz = None
        city = message.text.strip() if message.text else None
        location = message.location
        tf = TimezoneFinder()
        
        if location:
            tz = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            if not city:
                url = f'https://nominatim.openstreetmap.org/reverse?lat={location.latitude}&lon={location.longitude}&format=json'
                resp = requests.get(url, headers={'User-Agent': 'BirthdayBot'})
                data = resp.json()
                if data and 'address' in data:
                    city = data['address'].get('city') or data['address'].get('town') or data['address'].get('village') or data['address'].get('municipality')
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
        
        await state.update_data(timezone=tz, city=city)
        
        timezone_message = get_timezone_message(city, tz)
        await message.answer(
            timezone_message,
            reply_markup=get_confirm_timezone_kb(tz, city)
        )
        await state.set_state(SettingsState.confirm_new_timezone)
        
    except Exception as e:
        logger.error(f'Ошибка при определении часового пояса: {e}', exc_info=True)
        await message.answer('❗ Произошла ошибка при определении часового пояса. Попробуйте ещё раз или отправьте геолокацию.')

@router.callback_query(F.data.startswith('confirm_timezone:'), SettingsState.confirm_new_timezone)
async def confirm_timezone_change_handler(callback: CallbackQuery, state: FSMContext):
    tz = callback.data.split(':', 1)[1]
    user_data = await state.get_data()
    city = user_data.get('city')
    
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.timezone = tz
            user.city = city
        else:
            user = User(user_id=callback.from_user.id, timezone=tz, city=city, notifications_enabled=True)
            session.add(user)
        await session.commit()

    timezone_message = get_timezone_message(city, tz)
    await callback.message.edit_text(f'{timezone_message}\n\n✅ Часовой пояс обновлён!')
    await callback.message.answer('Меню', reply_markup=get_main_menu_kb())
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == 'change_timezone', SettingsState.confirm_new_timezone)
async def change_timezone_change_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text('Пожалуйста, отправьте новый город или поделитесь геолокацией для определения часового пояса.')
    await callback.message.answer('Отправьте новый город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(SettingsState.waiting_for_new_timezone)
    await callback.answer()

# Основные команды меню
@router.message(F.text & F.text.strip().lower() == 'сколько дней до дня рождения?')
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
        if days == 1:
            await message.answer('🎉 Ваш день рождения уже завтра! 🎂')
        elif days == 0:
            await message.answer('🎉 С ДНЁМ РОЖДЕНИЯ! 🎂')
        else:
            await message.answer(f'🎂 До вашего дня рождения осталось <b>{days}</b> дней!', parse_mode='HTML')

@router.message(F.text & F.text.strip().lower() == 'сколько дней со дня рождения?')
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

@router.message(F.text & F.text.strip().lower() == 'изменить дату')
async def change_birthday_menu(message: Message, state: FSMContext):
    await message.answer('Выберите год своего рождения:', reply_markup=get_years_kb(2000))
    await state.set_state(SettingsState.waiting_for_new_birthday)

@router.message(SettingsState.waiting_for_new_birthday)
async def set_new_birthday(message: Message, state: FSMContext):
    date_text = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_text):
        await message.answer('❗ Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 11.11.2000)')
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
            user.notifications_enabled = True
        else:
            user = User(user_id=message.from_user.id, birthday=birthday, notifications_enabled=True)
            session.add(user)
        await session.commit()

    await message.answer('Дата рождения обновлена!')
    await state.clear()

@router.message(F.text & F.text.strip().lower() == 'изменить часовой пояс')
async def change_timezone_menu(message: Message, state: FSMContext):
    await message.answer('Отправьте новый город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
    await state.set_state(SettingsState.waiting_for_new_timezone)

@router.message(F.text & F.text.strip().lower() == 'мои настройки')
async def show_settings(message: Message):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer('Вы еще не завершили регистрацию!')
            return

        settings_text = "📊 Ваши настройки:\n\n"
        
        if user.birthday:
            settings_text += f"🎂 Дата рождения: {user.birthday.strftime('%d.%m.%Y')}\n"
        else:
            settings_text += "🎂 Дата рождения: не указана\n"
            
        if user.timezone and user.city:
            timezone_message = get_timezone_message(user.city, user.timezone)
            settings_text += f"{timezone_message}\n"
        else:
            settings_text += "🌍 Часовой пояс: не указан\n"
            
        if user.notifications_enabled:
            settings_text += "🔔 Уведомления: включены"
        else:
            settings_text += "🔕 Уведомления: отключены"

        await message.answer(settings_text)

@router.message(F.text & F.text.strip().lower() == 'отключить уведомления')
async def disable_notifications_menu(message: Message):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer('❌ Вы еще не зарегистрированы в боте.')
            return

    await message.answer(
        '⚠️ Вы уверены, что хотите отключить уведомления?\n\n'
        'После отключения:\n'
        '• Все ваши данные будут полностью удалены из базы данных\n'
        '• Вы не будете получать напоминания о дне рождения\n'
        '• Для использования бота потребуется заново пройти регистрацию',
        reply_markup=get_disable_notifications_kb()
    )

@router.callback_query(F.data == 'confirm_disable_notifications')
async def confirm_disable_notifications(callback: CallbackQuery):
    async for session in get_db():
        result = await session.execute(select(User).where(User.user_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        if user:
            await session.delete(user)
            await session.commit()
            
            await callback.message.edit_text(
                '✅ Уведомления отключены!\n\n'
                '• Все ваши данные удалены из базы данных\n'
                '• Напоминания больше не будут приходить\n'
                '• Для использования бота нажмите /start'
            )
        else:
            await callback.message.edit_text('❌ Пользователь не найден в базе данных.')
    
    await callback.answer()

@router.callback_query(F.data == 'cancel_disable_notifications')
async def cancel_disable_notifications(callback: CallbackQuery):
    await callback.message.edit_text('❌ Отключение уведомлений отменено. Ваши данные сохранены.')
    await callback.answer()

@router.message(Command('state'))
async def show_state(message: Message, state: FSMContext):
    s = await state.get_state()
    await message.answer(f'Текущее состояние: {s}')

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

@router.callback_query(F.data.startswith('cal:year:'), RegisterState.waiting_for_birthday)
@router.callback_query(F.data.startswith('cal:year:'), SettingsState.waiting_for_new_birthday)
async def calendar_year_handler(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(':')[2])
    await state.update_data(year=year)
    await callback.message.edit_text(
        f'Выберите месяц',
        reply_markup=get_months_kb(year)
    )
    await callback.answer()

@router.callback_query(F.data.startswith('cal:month:'), RegisterState.waiting_for_birthday)
@router.callback_query(F.data.startswith('cal:month:'), SettingsState.waiting_for_new_birthday)
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

@router.callback_query(F.data.startswith('cal:day:'), RegisterState.waiting_for_birthday)
@router.callback_query(F.data.startswith('cal:day:'), SettingsState.waiting_for_new_birthday)
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

@router.callback_query(F.data.startswith('cal:confirm:'), RegisterState.waiting_for_birthday)
@router.callback_query(F.data.startswith('cal:confirm:'), RegisterState.confirm_birthday)
@router.callback_query(F.data.startswith('cal:confirm:'), SettingsState.waiting_for_new_birthday)
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
                user.notifications_enabled = True
            else:
                user = User(user_id=callback.from_user.id, birthday=iso_date, notifications_enabled=True)
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
                user.notifications_enabled = True
            else:
                user = User(user_id=callback.from_user.id, birthday=iso_date, notifications_enabled=True)
                session.add(user)
            await session.commit()
        await callback.message.edit_text(
            'Теперь отправьте ваш город или поделитесь геолокацией для определения часового пояса.'
        )
        await callback.message.answer('Отправьте город или поделитесь геолокацией:', reply_markup=get_timezone_share_kb())
        await state.set_state(RegisterState.waiting_for_timezone)
    await callback.answer()

# УНИВЕРСАЛЬНЫЙ обработчик для cal:change (работает в любом состоянии)
@router.callback_query(F.data == 'cal:change')
async def universal_calendar_change_handler(callback: CallbackQuery, state: FSMContext):
    """Универсальный обработчик для кнопки изменения даты в любом состоянии"""
    current_state = await state.get_state()
    
    if current_state == RegisterState.confirm_birthday.state:
        await state.set_state(RegisterState.waiting_for_birthday)
    elif current_state == SettingsState.waiting_for_new_birthday.state:
        await state.set_state(SettingsState.waiting_for_new_birthday)
    else:
        await state.set_state(RegisterState.waiting_for_birthday)
    
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(2000))
    await callback.answer()

@router.callback_query(F.data.startswith('cal:year_prev:'))
async def calendar_year_prev(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(':')[2])
    new_page = max(0, page - 1)
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(new_page))
    await callback.answer()

@router.callback_query(F.data.startswith('cal:year_next:'))
async def calendar_year_next(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(':')[2])
    new_page = page + 1
    await callback.message.edit_text('Пожалуйста, выберите год своего рождения:', reply_markup=get_years_kb(new_page))
    await callback.answer()

@router.callback_query(F.data == 'cal:back_to_years')
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

@router.callback_query(F.data.startswith('cal:back_to_months:'))
async def calendar_back_to_months(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split(':')[2])
    await callback.message.edit_text('Выберите месяц', reply_markup=get_months_kb(year))
    await callback.answer()