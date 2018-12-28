from unittest import mock
import asyncio


def create_stub_future(result):
    f = asyncio.Future()
    f.set_result(result)
    return f


def mock_coroutine(result):
    m = mock.MagicMock()
    m.return_value = create_stub_future(result)
    return m
