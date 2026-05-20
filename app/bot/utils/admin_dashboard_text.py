"""Краткий KPI-блок для /admin — детали смотрим в Grafana."""

from html import escape


def format_admin_kpi_html(kpi: dict[str, float | int], grafana_url: str | None) -> str:
    total = int(kpi.get("total_users", 0))
    today = int(kpi.get("registered_today", 0))
    subs = int(kpi.get("users_with_subscription", 0))
    avg_cars = float(kpi.get("avg_cars_per_subscription", 0.0))

    grafana_line = ""
    if grafana_url:
        grafana_line = (
            f'\n<a href="{escape(grafana_url)}">Открыть полный дашборд в Grafana →</a>'
        )

    return (
        "<b>Сводка</b>\n\n"
        f"👥 Всего пользователей: <b>{total}</b>\n"
        f"🆕 Зарегистрированы сегодня: <b>{today}</b>\n"
        f"⭐ С активной подпиской: <b>{subs}</b>\n"
        f"🚗 Авто на подписку (среднее): <b>{avg_cars:.2f}</b>"
        + grafana_line
    )
