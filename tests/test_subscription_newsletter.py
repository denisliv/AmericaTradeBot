import pytest

from app.infrastructure.services import subscription_newsletter as newsletter


@pytest.mark.asyncio
async def test_newsletter_queue_returns_batch_with_retry_items():
    queue = newsletter.NewsletterQueue(max_retries=2, batch_size=2)
    await queue.add_subscriber("user-1")
    await queue.add_retry("user-2", retry_count=0)

    batch = await queue.get_batch()
    assert len(batch) == 2
    assert {item[0] for item in batch} == {"user-1", "user-2"}


@pytest.mark.asyncio
async def test_process_newsletter_batch_retries_on_failure(monkeypatch):
    queue = newsletter.NewsletterQueue(max_retries=2, batch_size=10)
    retried = []
    ok_subscriber = type("Subscriber", (), {"user_id": 1})()
    retry_subscriber = type("Subscriber", (), {"user_id": 2})()

    async def fake_send_newsletter_to_user(bot, subscriber, conn):
        if subscriber.user_id == 1:
            return True, ""
        return False, "temporary error"

    async def fake_add_retry(subscriber, retry_count):
        retried.append((subscriber, retry_count))

    monkeypatch.setattr(
        newsletter,
        "send_newsletter_to_user",
        fake_send_newsletter_to_user,
    )
    monkeypatch.setattr(queue, "add_retry", fake_add_retry)

    batch = [(ok_subscriber, 0), (retry_subscriber, 1)]
    await newsletter.process_newsletter_batch(None, None, queue, batch)

    assert retried == [(retry_subscriber, 1)]


@pytest.mark.asyncio
async def test_send_newsletter_to_user_ignores_assisted_subscriptions(monkeypatch):
    subscriber = type("Subscriber", (), {"user_id": 10, "name": "Denis"})()
    calls = {"self": 0, "assisted": 0}
    assert not hasattr(newsletter, "send_assisted_selection_cars")
    assert not hasattr(newsletter, "get_cars_for_assisted_selection")

    async def fake_get_user_subscriptions(conn, user_id):
        return []

    async def fake_send_self_selection_cars(bot, subscriber, cars_data):
        calls["self"] += 1
        return 1

    async def fake_get_cars_for_self_selection(subscription):
        return []

    monkeypatch.setattr(newsletter, "get_user_subscriptions", fake_get_user_subscriptions)
    monkeypatch.setattr(newsletter, "send_self_selection_cars", fake_send_self_selection_cars)
    monkeypatch.setattr(newsletter, "get_cars_for_self_selection", fake_get_cars_for_self_selection)

    success, error = await newsletter.send_newsletter_to_user(None, subscriber, None)

    assert success is True
    assert error == ""
    assert calls == {"self": 0, "assisted": 0}
