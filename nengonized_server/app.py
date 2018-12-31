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
        data = json.loads(message)
        result = self.schema.execute(
                data['query'], variables=data['variables'],
                context=self.context)
        if result.errors:
            for error in result.errors:
                self.logger.error(error)
        self.write_message(json.dumps(result.data))


class SubscriptionHandler(GraphQlHandler):
    def initialize(self, context, schema):
        super().initialize(context, schema)
        self.subscriptions = {}

    def on_message(self, message):
        data = json.loads(message)
        if data['action'] == 'subscribe':
            self.subscribe(
                data.get('subscriptionId', None), data['query'], data['variables'])
        elif data['action'] == 'unsubscribe':
            self.unsubscribe(data['subscriptionId'])
        else:
            self.logger.error("Invalid action: %s", data['action'])

    def subscribe(self, subscription_id, query, variables):
        result = self.schema.execute(
                query, variables=variables,
                context=self.context, allow_subscriptions=True)
        if hasattr(result, 'subscribe'):
            if subscription_id in self.subscriptions:
                self.unsubscribe(subscription_id)
            self.subscriptions[subscription_id] = result.subscribe(self.update)
        if hasattr(result, 'errors'):
            for error in result.errors:
                self.logger.error(error)

    def unsubscribe(self, subscription_id):
        self.subscriptions[subscription_id].dispose()
        del self.subscriptions[subscription_id]

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
