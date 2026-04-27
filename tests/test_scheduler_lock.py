import pytest

from app.bot.scheduler import SchedulerManager


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        return 1


@pytest.mark.asyncio
async def test_run_with_lock_executes_once():
    manager = SchedulerManager()
    manager._redis_client = FakeRedis()
    calls = []

    async def fake_job():
        calls.append("ran")

    await manager._run_with_lock("lock:test", fake_job(), lock_ttl_seconds=30)
    assert calls == ["ran"]


@pytest.mark.asyncio
async def test_run_with_lock_skips_when_lock_exists():
    manager = SchedulerManager()
    fake_redis = FakeRedis()
    fake_redis.store["lock:test"] = "occupied"
    manager._redis_client = fake_redis
    calls = []

    async def fake_job():
        calls.append("ran")

    await manager._run_with_lock("lock:test", fake_job(), lock_ttl_seconds=30)
    assert calls == []


@pytest.mark.asyncio
async def test_download_csv_wrapper_uses_redis_lock(monkeypatch):
    manager = SchedulerManager()
    fake_redis = FakeRedis()
    fake_redis.store["lock:download_csv"] = "occupied"
    manager._redis_client = fake_redis
    calls = []

    async def fake_download_csv(url):
        calls.append(url)

    monkeypatch.setattr("app.bot.scheduler.download_csv", fake_download_csv)

    await manager._download_csv_wrapper("https://example.com/sales.csv")

    assert calls == []
