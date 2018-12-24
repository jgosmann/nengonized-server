import asyncio
import logging
from unittest import mock
from subprocess import PIPE
import sys

import pytest

from nengonized_server.kernel_management import Kernel


class CreateProcessMock(mock.MagicMock):
    def __init__(self):
        super().__init__()
        self.proc = ProcessMock()
        f = asyncio.Future()
        f.set_result(self.proc)
        self.return_value = f


class ProcessMock(mock.NonCallableMagicMock):
    def __init__(self):
        super().__init__()
        self.stdout = StreamMock([b'{"field": 42}\n', b'\n', b'stdout\n'])
        self.stderr = StreamMock([b'stderr\n'])

    async def wait(self):
        pass


class StreamMock(mock.MagicMock):
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
            'asyncio.create_subprocess_exec', CreateProcessMock()) as cse_mock:
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
