import asyncio
import logging
import json
from subprocess import PIPE
import sys

import rx
import websockets


logger = logging.getLogger(__name__)


class Kernel(object):
    def __init__(self, *args):
        self.logger = logger.getChild(f'Kernel({id(self)})')
        self.args = args
        self.proc = None
        self.conf = None

    async def __aenter__(self):
        self.proc = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'nengonized_kernel', *self.args,
                stdout=PIPE, stderr=PIPE)
        self.logger.info("Started kernel with arguments %s.", self.args)

        asyncio.get_running_loop().create_task(
                self._pipe(self.proc.stderr, 'stderr', logging.ERROR))

        self.conf = await self._read_json_conf(self.proc.stdout)
        self.logger.info("Received kernel configuration %s.", self.conf)
        asyncio.get_running_loop().create_task(
                self._pipe(self.proc.stdout, 'stdout', logging.INFO))

        return self

    async def _read_json_conf(self, stream):
        lines = []
        while len(lines) == 0 or lines[-1] != b'\n':
            lines.append(await stream.readline())
        return json.loads(b''.join(lines))

    async def _pipe(self, src, name, lvl):
        logger = self.logger.getChild(name)
        async for line in src:
            logger.log(lvl, '%s', line.decode())

    async def __aexit__(self, exc_type, exc, tb):
        self.logger.info("Terminating kernel.")
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=1)
        except asyncio.TimeoutError:
            self.logger.warning("Kernel did not terminate in time, killing.")
            self.proc.kill()


class ConnectedKernel(object):
    def __init__(self, kernel):
        self.kernel = kernel
        self.gql_connection = None
        self.gql_socket = None
        self.gql_connection_lock = asyncio.Lock()

    async def __aenter__(self):
        await self.kernel.__aenter__()
        self.gql_connection = websockets.connect(
            self._get_connection_string(
                self.kernel.conf['graphql'][0]))
        self.gql_socket = await self.gql_connection.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        async with self.gql_connection_lock:
            await self.gql_connection.__aexit__(exc_type, exc, tb)
        await self.kernel.__aexit__(exc_type, exc, tb)

    @classmethod
    def _get_connection_string(cls, addr):
        is_ipv6 = len(addr) > 2
        if is_ipv6:
            return f'ws://[{addr[0]}]:{addr[1]}'
        else:
            return f'ws://{addr[0]}:{addr[1]}'

    async def query(self, query_text, variables=None):
        async with self.gql_connection_lock:
            await self.gql_socket.send(json.dumps({
                'query': query_text, 'variables': variables}))
            return await self.gql_socket.recv()


class Reloadable(rx.core.ObservableBase):
    def __init__(self, wrapped):
        super().__init__()
        self.wrapped = wrapped
        self._n_calls_ongoing = 0
        self._cond_lock = asyncio.Condition()
        self._observers = []

    async def __aenter__(self):
        await self.wrapped.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        for observer in self._observers:
            if exc:
                observer.on_error(exc)
            else:
                observer.on_completed()
        return await self.wrapped.__aexit__(exc_type, exc, tb)

    async def reload(self):
        async with self._cond_lock:
            await self._cond_lock.wait_for(lambda: self._n_calls_ongoing == 0)
            await self.wrapped.__aexit__(None, None, None)
            await self.wrapped.__aenter__()
            self._notify_observers()

    async def call(self, method, *args, **kwargs):
        async with self._cond_lock:
            self._n_calls_ongoing += 1
        try:
            result = method(*args, **kwargs)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result
            return result
        finally:
            async with self._cond_lock:
                self._n_calls_ongoing -= 1

    def _notify_observers(self):
        for observer in self._observers:
            observer.on_next(self)

    def _subscribe_core(self, observer, scheduler=None):
        self._observers.append(observer)
        def dispose(observer=observer):
            self._observers.remove(observer)
        return dispose


class Subscribable(Reloadable):
    def __init__(self, wrapped):
        super().__init__(wrapped)
        self._subscriptions = []

    async def subscribe(self, observer, method, *args, **kwargs):
        subscription = (observer, method, args, kwargs)
        self._subscriptions.append(subscription)
        await self._update_subscriber(subscription)
        return subscription

    def unsubscribe(self, subscription):
        self._subscriptions.remove(subscription)

    async def reload(self):
        await super().reload()
        await asyncio.gather(
                *(self._update_subscriber(s) for s in self._subscriptions))

    async def _update_subscriber(self, subscription):
        observer, method, args, kwargs = subscription
        observer.on_next(await self.call(method, *args, **kwargs))
