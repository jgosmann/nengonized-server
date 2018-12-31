import asyncio
from unittest import mock
import re

from nengonized_kernel.gql.testing import assert_gql_data_equals
import pytest
import rx

from nengonized_server.async_testing import mock_coroutine
from nengonized_server.gql.schema import schema


pytestmark = pytest.mark.asyncio


async def dummy_coro(*args, **kwargs):
    return '{ "model": { "label": "foo" } }'


async def complete_other_tasks():
    current_task = asyncio.current_task()
    other_tasks = (
            task for task in asyncio.all_tasks() if task is not current_task)
    await asyncio.gather(*other_tasks)


async def test_can_subscribe_to_kernel():
    context_mock = mock.MagicMock()
    context_mock.reloadable = rx.subjects.Subject()
    context_mock.reloadable.call = dummy_coro
    observer_mock = mock.MagicMock()
    obs = schema.execute(
            'subscription Sub { kernel { model { label } } }',
            context=context_mock, allow_subscriptions=True)
    obs.subscribe(observer_mock)

    await complete_other_tasks()
    observer_mock.on_next.assert_called_once()
    observer_mock.on_next.reset_mock()

    context_mock.reloadable.on_next(2)
    await complete_other_tasks()
    observer_mock.on_next.assert_called_once()
    assert_gql_data_equals(observer_mock.on_next.call_args[0][0], {
        'kernel': {'model': {'label': 'foo'}}
    })


async def test_supports_fragments():
    context_mock = mock.MagicMock()
    context_mock.reloadable = rx.subjects.Subject()
    context_mock.reloadable.call = mock.MagicMock()
    context_mock.reloadable.call.return_value = dummy_coro()
    observer_mock = mock.MagicMock()
    obs = schema.execute(
            'subscription Sub { kernel { model { ...fragmentName } } }\n'
            'fragment fragmentName on NengoNetwork { label }',
            context=context_mock, allow_subscriptions=True)
    obs.subscribe(observer_mock)
    await complete_other_tasks()

    context_mock.reloadable.call.assert_called_once()
    method, query = context_mock.reloadable.call.call_args[0]
    assert method is context_mock.kernel.query
    assert re.sub(r'\s+', '', query) == re.sub(r'\s+', '', '''
        query Sub { model { ...fragmentName } }
        fragment fragmentName on NengoNetwork { label }
    ''')


async def test_supports_variables():
    context_mock = mock.MagicMock()
    context_mock.reloadable = rx.subjects.Subject()
    context_mock.reloadable.call = mock.MagicMock()
    context_mock.reloadable.call.return_value = dummy_coro()
    observer_mock = mock.MagicMock()
    obs = schema.execute(
            '''subscription Sub($id: ID!) { kernel {
                node(id: $id) { ... on NengoEnsemble { label } } } }
            ''',
            context=context_mock, variables={'id': 'ID42'},
            allow_subscriptions=True)
    obs.subscribe(observer_mock)
    await complete_other_tasks()

    context_mock.reloadable.call.assert_called_once()
    method, query = context_mock.reloadable.call.call_args[0]
    variables = context_mock.reloadable.call.call_args[1]['variables']
    assert method is context_mock.kernel.query
    assert re.sub(r'\s+', '', query) == re.sub(r'\s+', '', '''
        query Sub($id: ID!) { node(id: $id) { ... on NengoEnsemble { label } } }
    ''')
    assert variables == {'id': 'ID42'}
