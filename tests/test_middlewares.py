from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message, User

from bot.middlewares import ErrorMiddleware, RateLimitMiddleware


def _msg_event(user_id: int = 1) -> MagicMock:
    message = MagicMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = user_id
    message.answer = AsyncMock()
    return message


async def test_rate_limit_allows_first_n_requests():
    middleware = RateLimitMiddleware(per_minute=3)
    handler = AsyncMock(return_value="ok")
    event = _msg_event()

    for _ in range(3):
        result = await middleware(handler, event, {})
        assert result == "ok"

    assert handler.await_count == 3


async def test_rate_limit_blocks_excess():
    middleware = RateLimitMiddleware(per_minute=2)
    handler = AsyncMock(return_value="ok")
    event = _msg_event()

    await middleware(handler, event, {})
    await middleware(handler, event, {})
    await middleware(handler, event, {})

    assert handler.await_count == 2
    event.answer.assert_awaited()
    assert "🐢" in event.answer.call_args.args[0] or "быстро" in event.answer.call_args.args[0].lower()


async def test_rate_limit_per_user_independent():
    middleware = RateLimitMiddleware(per_minute=1)
    handler = AsyncMock(return_value="ok")
    event_a = _msg_event(user_id=1)
    event_b = _msg_event(user_id=2)

    await middleware(handler, event_a, {})
    await middleware(handler, event_b, {})

    assert handler.await_count == 2


async def test_error_middleware_catches_and_replies():
    middleware = ErrorMiddleware()

    async def boom(event, data):
        raise RuntimeError("kaboom")

    event = _msg_event()
    await middleware(boom, event, {})

    event.answer.assert_awaited()
    assert "пошло не так" in event.answer.call_args.args[0].lower() or "ошибка" in event.answer.call_args.args[0].lower()
