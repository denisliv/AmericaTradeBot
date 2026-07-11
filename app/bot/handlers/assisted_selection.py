import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from psycopg.connection_async import AsyncConnection

from app.bot.handlers.consultation_request import start_consultation_phone_request
from app.bot.keyboards.keyboards_inline import (
    create_assisted_results_keyboard,
    create_choice_keyboard,
)
from app.bot.states.states import FSMFillAssistedSelectionForm
from app.infrastructure.database.selections import add_assisted_selection_request
from app.infrastructure.services.assisted_gallery import (
    build_top_media_group,
    make_ag_lead_callback,
    parse_ag_lead_callback,
    pick_top_assisted_gallery,
    safe_send_assisted_gallery_media_group,
)
from app.lexicon.lexicon_ru import (
    LEXICON_ASSISTED_GALLERY_RU,
    LEXICON_FORM_BUTTONS_RU,
    LEXICON_RU,
)

assisted_selection_router: Router = Router()

# Категория для заголовка ТОП-подборки (родительный падеж множественного числа)
_TOP_CATEGORY_BY_BODY = {
    "🚙 Кроссовер/SUV": "кроссоверов",
    "🚗 Седан/Хэтчбек": "седанов",
    "⚡Электромобиль": "электромобилей",
    "Еще не решил/разные варианты": "авто",
}


# Этот хэндлер будет срабатывать на кнопки "🙎‍♂️ Пока нужна помощь в выборе"
# и "🚗 Изменить запрос" на экранах этой ветки
@assisted_selection_router.callback_query(
    F.data.in_({"advice_button", "change_request_assisted"}),
    flags={"blocking": "blocking"},
)
async def process_advice_button_press(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text=LEXICON_RU["choose_body_style_text"],
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["body_style_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.set_state(FSMFillAssistedSelectionForm.get_body_style)


# Этот хэндлер будет срабатывать на выбор типа авто
@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_body_style)
)
async def process_body_type_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text=LEXICON_RU["choose_budget_text"],
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["budget_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.update_data(body_style=callback.data)
    await state.set_state(FSMFillAssistedSelectionForm.get_budget)


# Этот хэндлер будет срабатывать на выбор бюджета: шлет ТОП-подборку
# и переводит на экран консультации с отправкой номера
@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_budget),
    flags={"long_operation": "typing"},
)
async def process_budget_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await callback.answer(
        text="Подбираем варианты под Ваши критерии. Это не займет много времени...",
        show_alert=True,
    )

    user_dict = await state.get_data()
    body_style = user_dict["body_style"]
    budget = callback.data

    await add_assisted_selection_request(
        conn,
        user_id=callback.from_user.id,
        body_style=body_style,
        budget=budget,
    )

    # body_style/budget остаются в данных FSM: нужны для "Подобрать еще"
    # и контекста Bitrix-лида
    await state.set_state(None)
    await state.update_data(budget=budget)
    await _send_top_picks(callback, state, body_style=body_style, budget=budget)


async def _send_top_picks(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    body_style: str,
    budget: str,
) -> None:
    """ТОП-подборка с карточками и финальным сообщением с действиями."""
    picks = pick_top_assisted_gallery(body_style, budget)
    if not picks:
        # Примеров нет - сразу предлагаем консультацию, контекст уходит в Bitrix
        await callback.message.answer(text=LEXICON_RU["assisted_gallery_empty_text"])
        await start_consultation_phone_request(
            callback.message,
            state,
            extra_data={"body_style": body_style, "budget": budget},
        )
        return

    await callback.message.answer(
        text=LEXICON_ASSISTED_GALLERY_RU["top_header"](
            _TOP_CATEGORY_BY_BODY.get(body_style, "авто")
        )
    )
    first_name = callback.from_user.first_name or "Пользователь"
    for number, pick in enumerate(picks, 1):
        await safe_send_assisted_gallery_media_group(
            callback, build_top_media_group(first_name, pick)
        )
        await callback.message.answer(
            text="👇 Нажмите кнопку, чтобы получить расчёт цены под ключ в РБ:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"✅ Пример № {number}: {pick.display_title}",
                            callback_data=make_ag_lead_callback(pick),
                            style=ButtonStyle.PRIMARY,
                        )
                    ]
                ]
            ),
        )
        await asyncio.sleep(0.2)

    await callback.message.answer(
        text=LEXICON_RU["cars_describe_text"],
        reply_markup=create_assisted_results_keyboard(),
    )


# Этот хэндлер будет срабатывать на кнопку "Подобрать еще":
# присылает новую ТОП-подборку по тем же кузову и бюджету
@assisted_selection_router.callback_query(
    F.data == "else_car_button_assisted",
    flags={"long_operation": "typing", "blocking": "blocking"},
)
async def process_else_top_button_press(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    body_style = data.get("body_style")
    budget = data.get("budget")

    if not body_style or not budget:
        # Контекст утерян (например, рестарт бота) - начинаем подбор заново
        await callback.message.edit_text(
            text=LEXICON_RU["choose_body_style_text"],
            reply_markup=create_choice_keyboard(
                *LEXICON_FORM_BUTTONS_RU["body_style_buttons"], width=1
            ),
        )
        await callback.answer()
        await state.set_state(FSMFillAssistedSelectionForm.get_body_style)
        return

    await callback.answer()
    await _send_top_picks(callback, state, body_style=body_style, budget=budget)


# Этот хэндлер будет срабатывать на кнопку "✅ Пример № N" под карточкой подборки:
# показывает экран консультации, выбранный пример уходит в комментарий Bitrix-лида
@assisted_selection_router.callback_query(F.data.startswith("ag_lead|"))
async def process_assisted_gallery_lead(callback: CallbackQuery, state: FSMContext):
    parsed = parse_ag_lead_callback(callback.data)
    if not parsed:
        await callback.answer()
        return

    _car_folder, body_ru, budget_ru, display_title = parsed
    # Нажатая кнопка заменяется отметкой выбора, экран консультации приходит
    # новым сообщением внизу чата
    await callback.message.edit_text(
        text=LEXICON_RU["car_selected_text"](display_title)
    )
    await start_consultation_phone_request(
        callback.message,
        state,
        extra_data={
            "body_style": body_ru,
            "budget": budget_ru,
            "car_title": display_title,
        },
    )
    await callback.answer()
