import asyncio
import logging
from unittest import mock
from subprocess import PIPE
import sys

import pytest

from nengonized_server.kernel_management import ConnectedKernel, Kernel


def create_stub_future(result):
    f = asyncio.Future()
    f.set_result(result)
    return f


def mock_coroutine(result):
    m = mock.MagicMock()
    m.return_value = create_stub_future(result)
    return m


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
    @pytest.mark.asyncio
    async def test_on_enter_starts_kernel_with_given_arguments(self, cse_mock):
        async with Kernel('foo', 'bar') as kernel:
            cse_mock.assert_called_once_with(
                sys.executable, '-m', 'nengonized_kernel', 'foo', 'bar',
                stdout=PIPE, stderr=PIPE)

    @pytest.mark.asyncio
    async def test_on_exit_terminates_kernel(self, cse_mock):
        async with Kernel() as kernel:
            pass
        cse_mock.proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_reads_kernel_conf(self, cse_mock):
        async with Kernel() as kernel:
            assert kernel.conf == {'field': 42}

    @pytest.mark.asyncio
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


class KernelStub(mock.MagicMock):
    ipv4_conf = {'graphql': {'addresses': [('127.0.0.1', 12345)]}}
    ipv6_conf = {'graphql': {'addresses': [('::1', 12345, 0, 0)]}}

    def __init__(self, conf):
        super().__init__()
        self.conf = conf

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


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
    @pytest.mark.asyncio
    @pytest.mark.parametrize('conf,url', [
        (KernelStub.ipv4_conf, 'ws://127.0.0.1:12345'),
        (KernelStub.ipv6_conf, 'ws://[::1]:12345'),
    ])
    async def test_starts_kernel_and_connects(
            self, conf, url, ws_connect_mock, connection_mock):
        async with KernelStub(conf) as kernel_stub:
            async with ConnectedKernel(kernel_stub) as connected_kernel:
                ws_connect_mock.assert_called_once_with(url)

    @pytest.mark.asyncio
    async def test_disconnects(
            self, ws_connect_mock, connection_mock):
        async with KernelStub(KernelStub.ipv6_conf) as kernel_stub:
            async with ConnectedKernel(kernel_stub) as connected_kernel:
                pass
        connection_mock.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_can_send_queries_to_kernel(
            self, ws_connect_mock, connection_mock):
        connection_mock.recv = mock_coroutine('data')
        async with KernelStub(KernelStub.ipv6_conf) as kernel_stub:
            async with ConnectedKernel(kernel_stub) as connected_kernel:
                result = await connected_kernel.query('{ model { id } }')
                connection_mock.send.assert_called_once_with(
                        '{ model { id } }')
        assert result == 'data'
