from aiogram import Dispatcher, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from . import auth
from . import callback_data
from . import remind_later
from .. import dependencies
from ..drivers import driver_factory
from ..feed_processing import subscription


def _make_help():
    msg = (
        "/help выводит это сообщение\n"
        "/start регистрирует пользователя\n"
        "/subscribe подписывает пользователя на обновления\n"
        "/subscriptions возвращает список активных подписок\n"
        "/unsubscribe отписывает пользователя от обновлений"
    )
    return msg.strip()


deps = dependencies.get()
storage = RedisStorage2(
    host=deps.get_cfg().redis_host,
    port=deps.get_cfg().redis_port,
    prefix=deps.get_cfg().aiogram_fsm_prefix,
)
dp = Dispatcher(deps.get_bot(), storage=storage)
dp.middleware.setup(auth.AuthMiddleware())


@dp.message_handler(commands='start')
async def start_handler(message: types.Message):
    async with deps.get_db() as db:
        res = await db.users.register(
            str(message.from_id),
            str(message.from_user.username),
        )

    if res is True:
        await message.reply('Вы успешно зарегистрированы!')
    else:
        await message.reply('Произошла ошибка при регистрации')


@dp.message_handler(state='*', commands='cancel')
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply('Отменено')


@dp.message_handler(commands='help')
async def help_handler(message: types.Message):
    await message.reply(_make_help())


@dp.message_handler(commands='subscriptions')
async def subscriptions_handler(message: types.Message):
    async with deps.get_db() as db:
        user_subscription = subscription.UserSubscription(db)
        feeds = await user_subscription.get_user_feeds(str(message.from_id))
    data = []
    for feed in feeds:
        data.append(f'`{feed.get_url()}`')
    msg = 'Нет активных подписок'
    if data:
        data_str = '\n'.join(data)
        msg = f'Активные подписки:\n{data_str}'
    await message.reply(msg, types.ParseMode.MARKDOWN)


class NewSubscription(StatesGroup):
    url = State()


@dp.message_handler(commands='subscribe')
async def subscribe_handler(message: types.Message):
    await NewSubscription.url.set()
    await message.reply('Введи ссылку на фид')


@dp.message_handler(state=NewSubscription.url)
async def url_state(message: types.Message, state: FSMContext):
    factory = driver_factory.DriverFactory()
    url = message.text.strip()
    driver = factory.find_driver(url)
    await state.finish()
    if not driver:
        await message.reply('Кажется, я еще не умею обрабатывать такие ссылки')
        return
    async with deps.get_db() as db:
        user_subscription = subscription.UserSubscription(db)
        is_subscribed = await user_subscription.subscribe(
            str(message.from_id),
            driver,
            url,
        )
        if is_subscribed:
            await message.reply('Вы успешно подписаны')
            return
        await message.reply('Не удалось создать фид')


@dp.message_handler(commands='unsubscribe')
async def unsubscribe_hander(message: types.Message):
    chat_id = str(message.from_id)
    async with deps.get_db() as db:
        user_subscription = subscription.UserSubscription(db)
        feeds = await user_subscription.get_user_feeds(chat_id)

    if not feeds:
        await message.reply('Нет активных подписок')
        return

    keyboard_markup = types.InlineKeyboardMarkup(row_width=1)
    for feed in feeds:
        data = callback_data.CallbackData(
            method=callback_data.Methods.UNSUBSCRIBE,
            payload={'id': feed.get_id()},
        )
        keyboard_markup.add(types.InlineKeyboardButton(
            feed.get_url(),
            callback_data=data.serialize(),
        ))
    await message.reply(
        'Выбери фид от которого нужно отписаться',
        reply_markup=keyboard_markup
    )


@dp.callback_query_handler(
    callback_data.create_matcher(callback_data.Methods.UNSUBSCRIBE),
)
async def unsubscribe_callback(callback_query: types.CallbackQuery):
    data = callback_data.parse(callback_query.data)
    if not data:
        await callback_query.answer('Что-то пошло не так')
        return

    feed_id = data.payload['id']
    await callback_query.answer('Готово')
    user_id = str(callback_query.from_user.id)

    msg = 'Не удалось найти фид'
    async with deps.get_db() as db:
        user_subscription = subscription.UserSubscription(db)
        is_unsubscribed = await user_subscription.unsubscribe(
            user_id,
            feed_id,
        )
        if is_unsubscribed:
            msg = 'Вы успешно отписаны'
    await callback_query.message.edit_text(
        msg,
        reply_markup=types.InlineKeyboardMarkup(),
    )
    await callback_query.answer('Готово')


@dp.callback_query_handler(
    callback_data.create_matcher(callback_data.Methods.LATER)
)
async def later_callback(callback_query: types.CallbackQuery):
    data = callback_data.parse(callback_query.data)
    if not data:
        await callback_query.answer('Что-то пошло не так')
        return

    user_id = str(callback_query.from_user.id)
    message_id = callback_query.message.message_id

    await remind_later.button_callback(deps, user_id, message_id, data)

    await callback_query.answer('Готово')
