import json
import logging

import rx
from tornado.web import Application
from tornado.websocket import WebSocketHandler

from .gql.schema import schema


logger = logging.getLogger(__name__)


class GraphQlHandler(WebSocketHandler):
    def initialize(self, context, schema):
        self.logger = logger.getChild(self.__class__.__name__)
        self.context = context
        self.schema = schema

    def check_origin(self, origin):
        return True  # FIXME


class QueryHandler(GraphQlHandler):
    def on_message(self, message):
        result = self.schema.execute(message, context=self.context)
        if result.errors:
            for error in result.errors:
                self.logger.error(error)
        self.write_message(json.dumps(result.data))


class SubscriptionHandler(GraphQlHandler):
    def on_message(self, message):
        result = self.schema.execute(
                message, context=self.context, allow_subscriptions=True)
        if hasattr(result, 'subscribe'):
            result.subscribe(self.update)
        if hasattr(result, 'errors'):
            for error in result.errors:
                self.logger.error(error)

    def update(self, result):
        if result.errors:
            for error in result.errors:
                self.logger.error(error)
        self.write_message(json.dumps(result.data))

    def close():
        pass


def make_app(context):
    args = {'context': context, 'schema': schema}
    return Application([
        (r"/graphql", QueryHandler, args),
        (r"/subscription", SubscriptionHandler, args),
    ])
