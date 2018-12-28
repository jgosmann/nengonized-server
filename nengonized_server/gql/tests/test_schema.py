from unittest import mock
import re

import pytest

from nengonized_server.async_testing import mock_coroutine
from nengonized_server.gql.schema import schema


pytestmark = pytest.mark.asyncio

async def dummy_coro():
    return


async def test_can_subscribe_to_kernel():
    context_mock = mock.MagicMock()
    context_mock.subscribable.subscribe = mock_coroutine(None)
    context_mock.subscribable.subscribe.return_value = dummy_coro()
    observer_mock = mock.MagicMock()
    obs = schema.execute(
            'subscription Sub { kernel { model { label } } }',
            context=context_mock, allow_subscriptions=True)
    obs.subscribe(observer_mock)

    context_mock.subscribable.subscribe.assert_called_once()
    observer, method, query = (
            context_mock.subscribable.subscribe.call_args[0])
    assert method is context_mock.kernel.query
    assert re.sub(r'\s+', '', query) == '{model{label}}'

    observer.on_next('{ "model": { "label": "12345" } }')
    observer_mock.on_next.assert_called_once()
    assert observer_mock.on_next.call_args[0][0].data == {
            'kernel': { 'model': { 'label': '12345' } } }


async def test_supports_fragments():
    context_mock = mock.MagicMock()
    context_mock.subscribable.subscribe = mock_coroutine(None)
    context_mock.subscribable.subscribe.return_value = dummy_coro()
    observer_mock = mock.MagicMock()
    obs = schema.execute(
            'subscription Sub { kernel { model { ...fragmentName } } }\n'
            'fragment fragmentName on NengoNetwork { label }',
            context=context_mock, allow_subscriptions=True)
    obs.subscribe(observer_mock)

    context_mock.subscribable.subscribe.assert_called_once()
    observer, method, query = (
            context_mock.subscribable.subscribe.call_args[0])
    assert method is context_mock.kernel.query
    print(query)
    assert re.sub(r'\s+', '', query) == re.sub(r'\s+', '', '''
        { model { ...fragmentName } }
        fragment fragmentName on NengoNetwork { label }
    ''')

    observer.on_next('{ "model": { "label": "12345" } }')
    observer_mock.on_next.assert_called_once()
    assert observer_mock.on_next.call_args[0][0].data == {
            'kernel': { 'model': { 'label': '12345' } } }
