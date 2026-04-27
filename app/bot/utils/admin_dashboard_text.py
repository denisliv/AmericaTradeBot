def _fmt_row(title: str, values: dict[str, float], as_percent: bool = False) -> str:
    def _v(key: str) -> str:
        value = values.get(key, 0)
        if as_percent:
            return f"{value:.2f}%"
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.2f}"

    return (
        f"{title}: "
        f"<b>T:{_v('today')}</b> | "
        f"<b>7д:{_v('d7')}</b> | "
        f"<b>30д:{_v('d30')}</b> | "
        f"<b>Все:{_v('all_time')}</b>"
    )


def format_admin_dashboard_html(s: dict[str, dict[str, float] | dict]) -> str:
    conv = s.get("conversion", {})
    return (
        "<b>Статистика бота</b>\n"
        "<i>Формат: Сегодня | 7 дней | 30 дней | Все время</i>\n\n"
        "<b>Пользователи</b>\n"
        f"{_fmt_row('Всего пользователей', s['users_total'])}\n"
        f"{_fmt_row('Активные', s['users_active'])}\n"
        f"{_fmt_row('Забаненные', s['users_banned'])}\n"
        f"{_fmt_row('Неактивные', s['users_inactive'])}\n\n"
        "<b>Воронка self-selection</b>\n"
        f"{_fmt_row('Стартовали подбор', s['funnel_started'])}\n"
        f"{_fmt_row('Дошли до шага года', s['funnel_reached_year'])}\n"
        f"{_fmt_row('Дошли до шага аукциона', s['funnel_reached_auction'])}\n"
        f"{_fmt_row('Завершили поиск', s['funnel_completed'])}\n"
        f"{_fmt_row('Клики по лотам', s['clicked_lot'])}\n"
        f"{_fmt_row('Лиды self', s['leads_self'])}\n\n"
        "<b>Конверсии</b>\n"
        f"{_fmt_row('Поиск → Подписка', conv['search_to_subscription_rate'], as_percent=True)}\n"
        f"{_fmt_row('Поиск → Лид', conv['search_to_lead_rate'], as_percent=True)}\n"
        f"{_fmt_row('LLM → Лид', conv['llm_to_lead_rate'], as_percent=True)}\n\n"
        "<b>Качество выдачи</b>\n"
        f"{_fmt_row('Поиски с результатами', s['searches_with_results'])}\n"
        f"{_fmt_row('Поиски без результатов', s['searches_without_results'])}\n"
        f"{_fmt_row('ALL MODELS использовано', s['all_models_usage'])}\n"
        f"{_fmt_row('Среднее авто на поиск', conv['avg_cars_shown_per_search'])}\n\n"
        "<b>Операционные рассылки</b>\n"
        f"{_fmt_row('Подписочная: sent', s['newsletter_sent'])}\n"
        f"{_fmt_row('Подписочная: failed', s['newsletter_failed'])}\n"
        f"{_fmt_row('Подписочная: retried', s['newsletter_retried'])}\n"
        f"{_fmt_row('Промо: sent', s['promo_sent'])}\n"
        f"{_fmt_row('Промо: failed', s['promo_failed'])}\n"
        f"{_fmt_row('Blocked/Deactivated', s['blocked_or_deactivated'])}\n\n"
        "<b>Надежность UX / обработчиков</b>\n"
        f"{_fmt_row('Невалидные callback', s['invalid_callbacks'])}\n"
        f"{_fmt_row('Исключения в хендлерах', s['handler_exceptions'])}\n"
        f"{_fmt_row('Ошибки БД', s['db_errors'])}\n"
        f"{_fmt_row('Рестарты Redis-listener', s['redis_listener_restarts'])}\n\n"
        "<b>Дополнительно</b>\n"
        f"{_fmt_row('Подписки (всего)', s['subscriptions_total'])}\n"
        f"{_fmt_row('Заявки self', s['self_requests'])}\n"
        f"{_fmt_row('Сообщения в LLM', s['llm_messages'])}\n"
        f"{_fmt_row('Стартов LLM-чата', s['llm_chat_started'])}\n"
        f"{_fmt_row('Лиды из LLM', s['llm_lead_sent'])}"
    )
