import asyncio
import json
import os
import sys

from tornado.ioloop import IOLoop

from .app import make_app
from .filesystem import FileWatcher
from .kernel_management import ConnectedKernel, Kernel, Subscribable
from .gql.schema import Context, schema


requestShutdown = asyncio.Event()

async def start_nengonized():
    filename = sys.argv[1]
    fw = FileWatcher(filename)  # start first to not miss any changes
    kernel = ConnectedKernel(Kernel(filename))
    async with Subscribable(kernel) as subscribable:
        fw.callback = subscribable.reload
        context = Context(subscribable, kernel)
        app = make_app(context)
        app.listen(8998)
        await requestShutdown.wait()


asyncio.get_event_loop().create_task(start_nengonized())
IOLoop.current().start()
