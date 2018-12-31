import json
from unittest import mock

import graphene

from nengonized_server.app import QueryHandler, SubscriptionHandler


def create_handler(type_, **kwargs):
    return type_(mock.MagicMock(), mock.MagicMock(), **kwargs)


class GqlDummyRoot(graphene.ObjectType):
    value = graphene.String()
    error = graphene.String()

    def resolve_value(self, info):
        return 'foo'

    def resolve_error(self, info):
        raise Exception("An error.")


dummySchema = graphene.Schema(query=GqlDummyRoot)


class TestQueryHandler(object):
    def test_query(self):
        context = object()
        schema = mock.MagicMock()
        schema.execute.return_value = dummySchema.execute('{ value }')
        handler = create_handler(QueryHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps(
            {'query': 'input-msg', 'variables': {'var': 'value'}}))
        schema.execute.assert_called_once_with(
                'input-msg', variables={'var': 'value'}, context=context)
        handler.write_message.assert_called_once_with('{"value": "foo"}')

    def test_error_handling(self):
        context = object()
        schema = mock.MagicMock()
        schema.execute.return_value = dummySchema.execute('{ error }')
        handler = create_handler(QueryHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps(
            {'query': 'input-msg', 'variables': None}))
        schema.execute.assert_called_once_with(
                'input-msg', variables=None, context=context)
        handler.write_message.assert_called_once_with('{"error": null}')


class TestSubsriptionHandler(object):
    def test_query(self):
        context = object()
        schema = mock.MagicMock()
        observable_mock = mock.MagicMock()
        schema.execute.return_value = observable_mock
        handler = create_handler(
                SubscriptionHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps({
            'action': 'subscribe',
            'subscriptionId': '1',
            'query': 'input-msg',
            'variables': {'var': 'value'},
        }))
        schema.execute.assert_called_once_with(
                'input-msg', context=context, variables={'var': 'value'},
                allow_subscriptions=True)
        observable_mock.subscribe.assert_called_once()

        subscriber = observable_mock.subscribe.call_args[0][0]
        subscriber(dummySchema.execute('{ value }'))
        handler.write_message.assert_called_once_with('{"value": "foo"}')

    def test_subscription_error_handling(self):
        context = object()
        schema = mock.MagicMock()
        schema.execute.return_value = dummySchema.execute('{ error }')
        handler = create_handler(
                SubscriptionHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps({
            'action': 'subscribe',
            'subscriptionId': '1',
            'query': 'input-msg',
            'variables': None,
        }))
        schema.execute.assert_called_once_with(
                'input-msg', context=context, variables=None,
                allow_subscriptions=True)

    def test_update_error_handling(self):
        context = object()
        schema = mock.MagicMock()
        observable_mock = mock.MagicMock()
        schema.execute.return_value = observable_mock
        handler = create_handler(
                SubscriptionHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps({
            'action': 'subscribe',
            'subscriptionId': '1',
            'query': 'input-msg',
            'variables': None,
        }))
        schema.execute.assert_called_once_with(
                'input-msg', context=context, variables=None,
                allow_subscriptions=True)
        observable_mock.subscribe.assert_called_once()

        subscriber = observable_mock.subscribe.call_args[0][0]
        subscriber(dummySchema.execute('{ error }'))
        handler.write_message.assert_called_once_with('{"error": null}')

    def test_unsubscribe(self):
        context = mock.MagicMock()
        schema = mock.MagicMock()
        disposable_mock = mock.MagicMock()
        observable_mock = mock.MagicMock()
        observable_mock.subscribe.return_value = disposable_mock
        schema.execute.return_value = observable_mock
        handler = create_handler(
                SubscriptionHandler, context=context, schema=schema)
        handler.write_message = mock.MagicMock()

        handler.on_message(json.dumps({
            'action': 'subscribe',
            'subscriptionId': '1',
            'query': 'input-msg',
            'variables': {},
        }))

        handler.on_message(json.dumps({
            'action': 'unsubscribe',
            'subscriptionId': '1',
        }))
        disposable_mock.dispose.assert_called_once()
