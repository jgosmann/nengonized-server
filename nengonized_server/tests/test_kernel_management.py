import asyncio
import json
import logging
from unittest import mock
from subprocess import PIPE
import sys

import pytest

from nengonized_server.async_testing import create_stub_future, mock_coroutine
from nengonized_server.kernel_management import (
        ConnectedKernel, Kernel, Reloadable, Subscribable)


pytestmark = pytest.mark.asyncio


class CreateProcessStub(mock.MagicMock):
    def __init__(self):
        super().__init__()
        self.proc = ProcessStub()
        self.return_value = create_stub_future(self.proc)


class ProcessStub(mock.NonCallableMagicMock):
    def __init__(self):
        super().__init__()
        self.stdout = StreamStub([b'{"field": 42}\n', b'\n', b'stdout\n'])
        self.stderr = StreamStub([b'stderr\n'])

    async def wait(self):
        pass


class StreamStub(mock.MagicMock):
    def __init__(self, lines):
        super().__init__()
        self.line_iter = iter(lines)

    async def readline(self):
        return next(self.line_iter)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.line_iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture
async def cse_mock():
    with mock.patch(
            'asyncio.create_subprocess_exec', CreateProcessStub()) as cse_mock:
        yield cse_mock


class TestKernel(object):
    async def test_on_enter_starts_kernel_with_given_arguments(self, cse_mock):
        async with Kernel('foo', 'bar') as kernel:
            cse_mock.assert_called_once_with(
                sys.executable, '-m', 'nengonized_kernel', 'foo', 'bar',
                stdout=PIPE, stderr=PIPE)

    async def test_on_exit_terminates_kernel(self, cse_mock):
        async with Kernel() as kernel:
            pass
        cse_mock.proc.terminate.assert_called_once()

    async def test_reads_kernel_conf(self, cse_mock):
        async with Kernel() as kernel:
            assert kernel.conf == {'field': 42}

    async def test_logs_kernel_stdout_and_stderr(self, cse_mock):
        kernel = Kernel()
        kernel.logger = mock.MagicMock()
        child_logger = mock.MagicMock()
        kernel.logger.getChild.return_value = child_logger
        async with kernel:
            pass
        child_logger.log.assert_has_calls([
                mock.call(logging.INFO, '%s', 'stdout\n'),
                mock.call(logging.ERROR, '%s', 'stderr\n'),
                ], any_order=True)


class KernelMock(mock.NonCallableMagicMock):
    ipv4_conf = {'graphql': [('127.0.0.1', 12345)]}
    ipv6_conf = {'graphql': [('::1', 12345, 0, 0)]}

    def __init__(self, conf=ipv6_conf):
        super().__init__()
        self.conf = conf
        self.pass_enter = asyncio.Event()
        self.pass_enter.set()
        self.__aenter__ = mock_coroutine(self)
        self.__aexit__ = mock_coroutine(None)

    async def __aenter__(self):
        await self.pass_enter.wait()
        self.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return self.__aexit__(exc_type, exc, tb)


@pytest.fixture
def connection_mock():
    m = mock.MagicMock()
    m.__aenter__ = mock_coroutine(m)
    m.__aexit__ = mock_coroutine(None)
    m.send = mock_coroutine(None)
    return m


@pytest.fixture
def ws_connect_mock(connection_mock):
    with mock.patch('websockets.connect') as ws_connect_mock:
        ws_connect_mock.return_value = connection_mock
        yield ws_connect_mock


class TestConnectedKernel(object):
    @pytest.mark.parametrize('conf,url', [
        (KernelMock.ipv4_conf, 'ws://127.0.0.1:12345'),
        (KernelMock.ipv6_conf, 'ws://[::1]:12345'),
    ])
    async def test_starts_kernel_and_connects(
            self, conf, url, ws_connect_mock, connection_mock):
        kernel_mock = KernelMock(conf)
        async with ConnectedKernel(kernel_mock) as connected_kernel:
            kernel_mock.__aenter__.assert_called_once()
            ws_connect_mock.assert_called_once_with(url)

    async def test_disconnects_stops_kernel(
            self, ws_connect_mock, connection_mock):
        kernel_mock = KernelMock()
        async with ConnectedKernel(kernel_mock) as connected_kernel:
            pass
        connection_mock.__aexit__.assert_called_once()
        kernel_mock.__aexit__.assert_called_once()

    async def test_can_send_queries_to_kernel(
            self, ws_connect_mock, connection_mock):
        connection_mock.recv = mock_coroutine('data')
        async with ConnectedKernel(KernelMock()) as connected_kernel:
            result = await connected_kernel.query(
                    '{ model { id } }', variables={'var': 'value'})
            connection_mock.send.assert_called_once_with(json.dumps(
                {'query': '{ model { id } }', 'variables': {'var': 'value'}}))
        assert result == 'data'


class TestReloadable(object):
    async def test_enters_and_exits_wrapped_object(self):
        kernel_mock = KernelMock()
        async with Reloadable(kernel_mock) as reloadable:
            kernel_mock.__aenter__.assert_called_once()
        kernel_mock.__aexit__.assert_called_once()

    async def test_exits_and_enters_wapped_object_on_reload(self):
        kernel_mock = KernelMock()
        async with Reloadable(kernel_mock) as reloadable:
            kernel_mock.__aenter__.reset_mock()
            await reloadable.reload()
            kernel_mock.__aexit__.assert_called_once()
            kernel_mock.__aenter__.assert_called_once()

    async def test_forwards_calls(self):
        kernel_mock = KernelMock()
        async with Reloadable(kernel_mock) as reloadable:
            kernel_mock.fn.return_value = 42
            retval = await reloadable.call(kernel_mock.fn, 1, 2, kwarg=3)
            kernel_mock.fn.assert_called_once_with(1, 2, kwarg=3)
            assert retval == 42

    async def test_queues_call_until_reloaded(self):
        kernel_mock = KernelMock()
        async with Reloadable(kernel_mock) as reloadable:
            kernel_mock.pass_enter.clear()
            reload_task = asyncio.get_event_loop().create_task(
                    reloadable.reload())
            call_task = asyncio.get_event_loop().create_task(
                    reloadable.call(kernel_mock.fn))
            kernel_mock.fn.assert_not_called()
            kernel_mock.pass_enter.set()
            await call_task
            kernel_mock.fn.assert_called_once()

    async def test_queues_reload_until_calls_finished(self):
        cont = asyncio.Event()
        async def fn():
            await cont.wait()

        kernel_mock = KernelMock()
        async with Reloadable(kernel_mock) as reloadable:
            kernel_mock.__aexit__.reset_mock()
            call_task = asyncio.get_event_loop().create_task(
                    reloadable.call(fn))
            reload_task = asyncio.get_event_loop().create_task(
                    reloadable.reload())
            kernel_mock.__aexit__.assert_not_called()
            cont.set()
            await call_task
            await reload_task
            kernel_mock.__aexit__.assert_called_once()


class TestSubscribableKernel(object):
    async def test_notifies_subscriber_on_subcription(self):
        dummy = mock.MagicMock()
        dummy.__aenter__ = mock_coroutine(self)
        dummy.__aexit__ = mock_coroutine(None)
        dummy.fn.return_value = 42
        observer = mock.MagicMock()

        async with Subscribable(dummy) as subscribable:
            await subscribable.subscribe(observer, dummy.fn, 1, 2, three=3)
        dummy.fn.assert_called_once_with(1, 2, three=3)
        observer.on_next.assert_called_once_with(42)

    async def test_notifies_subscriber_on_reload(self):
        dummy = mock.MagicMock()
        dummy.__aenter__ = mock_coroutine(self)
        dummy.__aexit__ = mock_coroutine(None)
        dummy.fn.return_value = 0
        observer = mock.MagicMock()

        async with Subscribable(dummy) as subscribable:
            await subscribable.subscribe(observer, dummy.fn, 1, 2, three=3)
            dummy.fn.reset_mock()
            dummy.fn.return_value = 42
            observer.on_next.reset_mock()

            await subscribable.reload()

        dummy.fn.assert_called_once_with(1, 2, three=3)
        observer.on_next.assert_called_once_with(42)
