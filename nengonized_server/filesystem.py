import asyncio
import os


class FileWatcher(object):
    def __init__(self, filename, callback=None, poll_interval=0.5):
        self.filename = filename
        self.callback = callback
        self.poll_interval = poll_interval
        self._last_load = os.stat(self.filename).st_mtime
        self._task = None

    async def watch(self):
        while True:
            await asyncio.sleep(self.poll_interval)
            await self._check_for_change()

    async def _check_for_change(self):
        if self.callback is None:
            return
        mtime = os.stat(self.filename).st_mtime
        if mtime > self._last_load:
            self._last_load = mtime
            result = self.callback()
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result

    def start_watching(self, loop=None):
        if loop is None:
            loop = asyncio.get_running_loop()
        assert self._task is None
        self._task = loop.create_task(self.watch())

    async def stop_watching(self):
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
