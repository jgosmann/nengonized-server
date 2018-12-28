import asyncio
from unittest import mock

import pytest

from nengonized_server.filesystem import FileWatcher


@pytest.fixture
def stat_mock():
    with mock.patch('os.stat') as stat_mock:
        yield stat_mock


class DummyStatValues(object):
    def __init__(self, st_mtime):
        self.st_size = 42
        self.st_mtime = st_mtime


@pytest.mark.asyncio
async def test_file_watcher_notifies_about_file_changes(stat_mock):
    stat_mock.return_value = DummyStatValues(st_mtime=42)
    callback = mock.MagicMock()
    fw = FileWatcher('path', callback, poll_interval=0.01)
    fw.start_watching()

    try:
        stat_mock.return_value = DummyStatValues(st_mtime=43)
        await asyncio.sleep(0.02)
        callback.assert_called_once()
    finally:
        await fw.stop_watching()


@pytest.mark.asyncio
async def test_file_watcher_notifies_about_event_before_setting_callback(
        stat_mock):
    stat_mock.return_value = DummyStatValues(st_mtime=42)
    callback = mock.MagicMock()
    fw = FileWatcher('path', poll_interval=0.01)
    fw.start_watching()

    try:
        stat_mock.return_value = DummyStatValues(st_mtime=43)
        await asyncio.sleep(0.02)
        callback.assert_not_called()
        fw.callback = callback
        await asyncio.sleep(0.02)
        callback.assert_called_once()
    finally:
        await fw.stop_watching()
