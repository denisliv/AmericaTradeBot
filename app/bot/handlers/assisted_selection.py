import asyncio

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
)
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.bot.states.states import FSMFillAssistedSelectionForm, FSMFillPhoneForm
from app.infrastructure.database.db import (
    add_assisted_selection_request,
)
from app.infrastructure.services.assisted_gallery import (
    build_assisted_gallery_media_group,
    make_ag_lead_callback,
    parse_ag_lead_callback,
    pick_random_assisted_gallery,
    safe_send_assisted_gallery_media_group,
)
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

assisted_selection_router: Router = Router()


@assisted_selection_router.callback_query(
    F.data.in_({"advice_button", "new_search_button_assisted"}),
    flags={"blocking": "blocking"},
)
async def process_advice_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Укажите предпочтительный кузов автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["body_style_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.set_state(FSMFillAssistedSelectionForm.get_body_style)


@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_body_style)
)
async def process_body_type_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Укажите в какой бюджет планируете покупку:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["budget_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.update_data(body_style=callback.data)
    await state.set_state(FSMFillAssistedSelectionForm.get_budget)


async def _send_one_assisted_gallery_pick(
    callback: CallbackQuery,
    *,
    body_style: str,
    budget: str,
    number: int,
) -> tuple[list[tuple[str, str]], int]:
    """Возвращает (кнопки для клавиатуры, следующий номер)."""
    pick = pick_random_assisted_gallery(body_style, budget)
    data_buttons: list[tuple[str, str]] = []
    if not pick:
        return data_buttons, number

    media = build_assisted_gallery_media_group(
        callback.from_user.first_name or "Пользователь", pick
    )
    ok = await safe_send_assisted_gallery_media_group(callback, media)
    if ok:
        data_buttons.append(
            (
                f"✅ Пример № {number}: {pick.display_title}",
                make_ag_lead_callback(pick),
            )
        )
        number += 1
    await asyncio.sleep(0.2)
    return data_buttons, number


@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_budget),
    flags={"long_operation": "typing"},
)
async def process_budget_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await state.update_data(budget=callback.data)

    await callback.answer(
        text="Подбираем варианты под Ваши критерии. Это не займет много времени...",
        show_alert=True,
    )

    user_dict = await state.get_data()
    body_style = user_dict["body_style"]
    budget = user_dict["budget"]

    await add_assisted_selection_request(
        conn,
        user_id=callback.from_user.id,
        body_style=body_style,
        budget=budget,
    )
    await state.clear()

    data_buttons, _ = await _send_one_assisted_gallery_pick(
        callback,
        body_style=body_style,
        budget=budget,
        number=1,
    )

    if not data_buttons:
        await callback.message.answer(
            text=LEXICON_RU["assisted_gallery_empty_text"],
            reply_markup=create_choice_keyboard(
                "new_search_button_assisted",
                "application_for_selection_button",
                width=1,
            ),
        )
        return

    await state.update_data(
        body_style=body_style,
        budget=budget,
        old_data_buttons=data_buttons,
        number=len(data_buttons) + 1,
        search_type="assisted",
    )

    await callback.message.answer(
        text=LEXICON_RU["assisted_gallery_result_text"],
        reply_markup=create_auto_keyboard(
            data_buttons, else_car=True, search_type="assisted"
        ),
    )


@assisted_selection_router.callback_query(
    F.data == "else_car_button_assisted", flags={"long_operation": "typing"}
)
async def process_else_car_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer()

    user_data = await state.get_data()
    body_style = user_data.get("body_style")
    budget = user_data.get("budget")
    old_data_buttons = user_data.get("old_data_buttons", [])
    number = user_data.get("number", 1)

    if not body_style or not budget:
        await callback.message.answer(
            text=LEXICON_RU["no_more_cars_text"],
            reply_markup=create_choice_keyboard(
                "new_search_button_assisted",
                "application_for_selection_button",
                width=1,
            ),
        )
        return

    new_buttons, number = await _send_one_assisted_gallery_pick(
        callback,
        body_style=body_style,
        budget=budget,
        number=number,
    )

    if not new_buttons:
        await callback.message.answer(
            text=LEXICON_RU["assisted_gallery_empty_text"],
            reply_markup=create_choice_keyboard(
                "new_search_button_assisted",
                "application_for_selection_button",
                width=1,
            ),
        )
        return

    all_data_buttons = old_data_buttons + new_buttons
    await state.update_data(
        body_style=body_style,
        budget=budget,
        old_data_buttons=all_data_buttons,
        number=number,
        search_type="assisted",
    )

    await callback.message.answer(
        text=LEXICON_RU["assisted_gallery_result_text"],
        reply_markup=create_auto_keyboard(
            all_data_buttons, else_car=True, search_type="assisted"
        ),
    )


@assisted_selection_router.callback_query(F.data.startswith("ag_lead|"))
async def process_assisted_gallery_lead(callback: CallbackQuery, state: FSMContext):
    parsed = parse_ag_lead_callback(callback.data)
    if not parsed:
        await callback.answer()
        return

    _car_folder, body_ru, budget_ru, display_title = parsed
    name = callback.from_user.first_name or "Пользователь"

    if callback.from_user.username:
        await bitrix_send_data(
            tg_login=callback.from_user.username,
            tg_id=callback.from_user.id,
            data={
                "name": name,
                "car_title": display_title,
                "body_style": body_ru,
                "budget": budget_ru,
            },
            method="assisted_gallery",
        )
        await callback.message.edit_text(
            text=LEXICON_RU["phone_request_answer_text"],
            reply_markup=create_choice_keyboard(
                "back_to:main_menu",
                "contact_button",
            ),
        )
    else:
        msg = await callback.message.answer(
            text=LEXICON_RU["choose_phone_request_text"],
            reply_markup=create_call_request_keyboard(),
        )
        await state.update_data(
            old_message_id=msg.message_id,
            bitrix_method="assisted_gallery",
            name=name,
            car_title=display_title,
            body_style=body_ru,
            budget=budget_ru,
        )
        await state.set_state(FSMFillPhoneForm.get_phone)

    await callback.answer()
