from types import SimpleNamespace

from app.bot.scheduler import create_scheduler


def _fake_config() -> SimpleNamespace:
    return SimpleNamespace(
        copart=SimpleNamespace(url="https://example.com/sales.csv"),
        scheduler=SimpleNamespace(
            timezone="Europe/Minsk",
            csv_interval_minutes=45,
            newsletter_hour=7,
            newsletter_minute=5,
            posts_day_of_week="mon",
            posts_hour=21,
            posts_minute=30,
        ),
    )


def test_create_scheduler_uses_schedule_from_config():
    manager = create_scheduler(
        _fake_config(), bot=None, db_pool=None, redis_client=None
    )

    jobs = {job.id: job for job in manager.get_jobs()}
    assert set(jobs) == {"download_csv", "daily_newsletter", "weekly_posts_broadcast"}

    assert str(manager.scheduler.timezone) == "Europe/Minsk"
    assert jobs["download_csv"].trigger.interval.total_seconds() == 45 * 60

    newsletter_trigger = str(jobs["daily_newsletter"].trigger)
    assert "hour='7'" in newsletter_trigger
    assert "minute='5'" in newsletter_trigger

    posts_trigger = str(jobs["weekly_posts_broadcast"].trigger)
    assert "day_of_week='mon'" in posts_trigger
    assert "hour='21'" in posts_trigger
    assert "minute='30'" in posts_trigger
