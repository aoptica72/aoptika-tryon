"""Aiogram bot for A-Optika; users' photos are processed in memory only."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from io import BytesIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup,
                           WebAppInfo)
from dotenv import load_dotenv

from .tryon import MAX_BYTES, TryOnError, catalog, render_photo_bytes

log = logging.getLogger(__name__)
router = Router()
MODEL = catalog()[0]


def privacy_url() -> str:
    return os.getenv('PRIVACY_URL', '').strip()


def main_keyboard() -> ReplyKeyboardMarkup:
    url = os.getenv('MINI_APP_URL', 'https://aoptica72.github.io/aoptika-tryon/telegram.html')
    if not url.startswith('https://'):
        raise ValueError('MINI_APP_URL должен начинаться с https://')
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='👓 Примерить очки', web_app=WebAppInfo(url=url))],
        [KeyboardButton(text='🛍 Каталог оправ'), KeyboardButton(text='❤️ Избранное')],
        [KeyboardButton(text='📍 Наши салоны'), KeyboardButton(text='📞 Консультант')],
    ], resize_keyboard=True, input_field_placeholder='Фото лица или вопрос консультанту')


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Согласен(на) на обработку фото на сервере', callback_data='consent:yes')],
        [InlineKeyboardButton(text='❌ Не согласен(на)', callback_data='consent:no')],
    ])


def actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❤️ В избранное', callback_data='favorite:add')],
        [InlineKeyboardButton(text='🔎 Узнать наличие', callback_data='action:stock')],
        [InlineKeyboardButton(text='📅 Записаться на примерку', callback_data='action:booking')],
        [InlineKeyboardButton(text='📞 Консультация', callback_data='action:consultation')],
    ])


@router.message(CommandStart())
async def welcome(message: Message, state: FSMContext) -> None:
    policy = privacy_url()
    server_note = (f'\nПолитика обработки данных: {policy}' if policy else
                   '\nПрямая обработка фото, отправленных в чат, пока отключена: сначала нужно опубликовать политику обработки данных.')
    await message.answer(
        'Добро пожаловать в виртуальную примерочную А-Оптика! 👓\n\n'
        'Нажмите «Примерить очки» ниже. В Mini App фотография обрабатывается прямо '
        'на вашем устройстве и не отправляется боту или на сервер А-Оптики. '
        'Перед выбором фото приложение попросит отдельное согласие.\n\n'
        'Если вы хотите отправить фотографию непосредственно в чат с ботом, '
        'это отдельный режим серверной обработки: сначала используйте команду /server_photo '
        'и подтвердите отдельное согласие.' + server_note,
        reply_markup=main_keyboard())


@router.message(Command('tryon'))
async def open_tryon(message: Message) -> None:
    """BotFather's /tryon command must always open the existing Mini App."""
    await message.answer('👓 Откройте виртуальную примерочную через кнопку ниже. Фото обрабатывается прямо на устройстве.',
                         reply_markup=main_keyboard())


@router.message(Command('server_photo'))
async def server_photo_consent(message: Message, state: FSMContext) -> None:
    if not privacy_url():
        await message.answer(
            'Отправка фото непосредственно в чат пока отключена. '
            'Используйте «👓 Примерить очки»: там фотография обрабатывается локально на устройстве.')
        return
    await message.answer(
        'В этом режиме фотография будет передана боту через Telegram и обработана в памяти сервера А-Оптики. '
        'Она не сохраняется в базе данных. Перед продолжением ознакомьтесь с политикой: '
        f'{privacy_url()}',
        reply_markup=consent_keyboard())


@router.callback_query(F.data.startswith('consent:'))
async def consent(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == 'consent:yes':
        if not privacy_url():
            await callback.answer('Для реальных пользователей сначала необходимо опубликовать политику обработки данных.', show_alert=True)
            return
        await state.update_data(consent=True)
        await callback.message.answer('Согласие на серверную обработку получено. Пришлите фото анфас или откройте примерочную 👇',
                                      reply_markup=main_keyboard())
    else:
        await state.update_data(consent=False)
        await callback.message.answer('Согласие на серверную обработку не получено. Вы можете пользоваться Mini App с локальной обработкой фото.')
    await callback.answer()


@router.message(Command('delete'))
async def delete_session(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Данные текущей сессии в памяти бота очищены. '
                         'Для удаления сообщений и фотографий из Telegram удалите их также из чата.')


@router.message(F.photo)
async def photo_tryon(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if not data.get('consent') or not privacy_url():
        await message.answer('Для отправки фото в чат сначала используйте /server_photo и подтвердите отдельное согласие. Для локальной примерки откройте Mini App.')
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > MAX_BYTES:
        await message.answer('Максимальный размер фото — 8 МБ. Пришлите уменьшенную фотографию.')
        return
    await message.answer('Обрабатываю фотографию и подбираю положение DACCHi 34355…')
    buffer = BytesIO()
    try:
        await bot.download(photo, destination=buffer)
        output = await asyncio.to_thread(render_photo_bytes, buffer.getvalue())
        await message.answer_photo(BufferedInputFile(output, filename='aoptika-dacchi-34355.jpg'),
                                   caption='DACCHi 34355 — виртуальная примерка. '
                                           'Размер и посадка приблизительные. '
                                           'Точную посадку проверит консультант в салоне.',
                                   reply_markup=actions_keyboard())
    except TryOnError as exc:
        await message.answer(str(exc))
    except Exception:
        log.exception('photo try-on failed (no photo data is logged)')
        await message.answer('Не удалось обработать фото. Попробуйте другое селфи или Mini App.')
    finally:
        buffer.close()


@router.message(F.web_app_data)
async def mini_app_data(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except (ValueError, TypeError):
        await message.answer('Неверный формат запроса.')
        return
    if not isinstance(payload, dict) or payload.get('sku') != MODEL['sku']:
        await message.answer('Модель не найдена.')
        return
    action = payload.get('action')
    if action == 'favorite':
        await state.update_data(favorite=MODEL['sku'])
        await message.answer('❤️ DACCHi 34355 добавлена в избранное.')
    elif action in ('stock', 'booking', 'consultation'):
        await handle_request(message, state, bot, action)
    else:
        await message.answer('Неизвестное действие.')


@router.callback_query(F.data.startswith('favorite:'))
async def favorite(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(favorite=MODEL['sku'])
    await callback.answer('Добавлено в избранное')


@router.callback_query(F.data.startswith('action:'))
async def actions(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    action = callback.data.removeprefix('action:')
    await callback.answer()
    await handle_request(callback.message, state, bot, action)


async def handle_request(message: Message, state: FSMContext, bot: Bot, action: str) -> None:
    if action not in ('stock', 'booking', 'consultation'):
        return
    if not os.getenv('ADMIN_CHAT_ID', '').strip():
        await message.answer('Приём заявок пока не подключён. Свяжитесь с салонами через https://aoptica.ru')
        return
    if not privacy_url():
        await message.answer('Приём заявок временно недоступен: политика обработки данных не настроена.')
        return
    await state.update_data(pending_action=action, contact_consent=False)
    await message.answer(
        'Для записи, запроса наличия или консультации нужны имя и телефон. Если вы согласитесь, они будут '
        'переданы сотруднику А-Оптики в служебном Telegram-чате для ответа на обращение. '
        f'Политика обработки данных: {privacy_url()}\n'
        'Можно отказаться: тогда заявку не отправим.',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='✅ Согласен(на) передать контакты', callback_data='contact:yes')],
            [InlineKeyboardButton(text='❌ Не согласен(на)', callback_data='contact:no')],
        ]))


@router.callback_query(F.data.startswith('contact:'))
async def consent_contacts(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get('pending_action'):
        await callback.answer('Сначала выберите запись или консультацию.', show_alert=True)
        return
    if callback.data == 'contact:no':
        await state.update_data(pending_action=None, contact_consent=False)
        await callback.message.answer('Вы отказались от передачи контактов. Заявка отменена.')
    elif callback.data == 'contact:yes' and privacy_url():
        await state.update_data(contact_consent=True)
        await callback.message.answer('Напишите имя и телефон одним сообщением (например: Иван +7 999 123-45-67). Для отмены — /cancel.')
    else:
        await callback.answer('Сначала необходимо опубликовать политику обработки данных.', show_alert=True)
        return
    await callback.answer()


@router.message(Command('cancel'))
async def cancel_request(message: Message, state: FSMContext) -> None:
    await state.update_data(pending_action=None, contact_consent=False)
    await message.answer('Заявка отменена.')


@router.message(F.text == '🛍 Каталог оправ')
async def show_catalog(message: Message) -> None:
    await message.answer('👓 DACCHi 34355\nРазмер: 54–17–146 мм\n'
                         'Цена и наличие: уточняются в салонах.\nДля примерки загрузите селфи.',
                         reply_markup=actions_keyboard())


@router.message(F.text == '❤️ Избранное')
async def show_favorite(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer('❤️ DACCHi 34355' if data.get('favorite') else
                         'Избранное пусто. Примерьте оправу и добавьте её в избранное.')


@router.message(F.text == '📍 Наши салоны')
async def salons(message: Message) -> None:
    await message.answer('Актуальные адреса и контакты салонов А-Оптика: https://aoptica.ru')


@router.message(F.text == '📞 Консультант')
async def consultant(message: Message, state: FSMContext, bot: Bot) -> None:
    await handle_request(message, state, bot, 'consultation')


@router.message(F.text)
async def request_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    action = data.get('pending_action')
    if not action:
        await message.answer('Выберите «Примерить очки» или пришлите фотографию анфас.')
        return
    if not data.get('contact_consent'):
        await message.answer('Сначала подтвердите согласие на передачу имени и телефона кнопкой выше.')
        return
    info = message.text.strip()
    if len(info) < 6 or len(info) > 250 or not 10 <= len(re.findall(r'\d', info)) <= 15:
        await message.answer('Укажите имя и номер телефона с 10–15 цифрами (не более 250 символов).')
        return
    chat_id = os.getenv('ADMIN_CHAT_ID', '').strip()
    if not chat_id:
        await message.answer('Заявки сейчас не подключены.')
        return
    title = {'stock': 'Запрос наличия', 'booking': 'Запись на примерку', 'consultation': 'Консультация'}[action]
    # Use HTML escaping to avoid Markdown injection; sending to configured operator only.
    from html import escape
    try:
        await bot.send_message(int(chat_id),
                               f'А-Оптика: {title}\nМодель: DACCHi 34355\n'
                               f'Покупатель: {escape(info)}\nTelegram ID: {message.from_user.id}',
                               parse_mode='HTML')
    except Exception:
        log.exception('failed to send new lead')
        await message.answer('Не удалось передать заявку. Позвоните в салон через https://aoptica.ru')
        return
    await state.update_data(pending_action=None, contact_consent=False)
    await message.answer('✅ Заявка передана сотруднику А-Оптики. С вами свяжутся.')


async def main() -> None:
    load_dotenv()
    token = os.getenv('BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('Укажите BOT_TOKEN в переменных окружения')
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=token)
    url = os.getenv('MINI_APP_URL', 'https://aoptica72.github.io/aoptika-tryon/telegram.html')
    if not url.startswith('https://'):
        raise RuntimeError('MINI_APP_URL должен быть HTTPS-адресом')
    try:
        # WebAppData.sendData is supported for Web Apps opened by a reply-keyboard button.
        # /start and /tryon always show that button; keep the default Telegram menu button unchanged.
        await bot.set_my_commands([
            BotCommand(command='start', description='Запустить примерочную'),
            BotCommand(command='tryon', description='Примерить DACCHi 34355'),
            BotCommand(command='delete', description='Очистить текущую сессию'),
            BotCommand(command='server_photo', description='Согласие на фото в чате'),
        ])
    except Exception:
        log.exception('Не удалось обновить список команд бота через Telegram API')
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    asyncio.run(main())