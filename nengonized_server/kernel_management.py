import asyncio
import logging
import json
from subprocess import PIPE
import sys

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
        self.conf = await self._read_json_conf(self.proc.stdout)
        self.logger.info("Received kernel configuration %s.", self.conf)

        asyncio.get_running_loop().create_task(
                self._pipe(self.proc.stdout, 'stdout', logging.INFO))
        asyncio.get_running_loop().create_task(
                self._pipe(self.proc.stderr, 'stderr', logging.ERROR))

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

    async def __aenter__(self):
        self.gql_connection = websockets.connect(self._get_connection_string(
            self.kernel.conf['graphql']['addresses'][0]))
        await self.gql_connection.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.gql_connection.__aexit__(exc_type, exc, tb)

    @classmethod
    def _get_connection_string(cls, addr):
        is_ipv6 = len(addr) > 2
        if is_ipv6:
            return f'ws://[{addr[0]}]:{addr[1]}'
        else:
            return f'ws://{addr[0]}:{addr[1]}'

    async def query(self, query_text):
        await self.gql_connection.send(query_text)
        return await self.gql_connection.recv()
