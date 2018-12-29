import asyncio
import json
import os
from subprocess import PIPE
import sys
import time

from graphene import Field, List, NonNull, ObjectType, relay, Scalar, Schema
from graphql.language.printer import print_ast
from nengonized_kernel.gql.schema import RootQuery as KernelRootQuery
from nengonized_kernel.gql.nengo_model_schema import NengoNetwork
import rx
import websockets

from .stitching import stitch


class Context(object):
    def __init__(self, subscribable, kernel):
        self.subscribable = subscribable
        self.kernel = kernel


class ServerRootQuery(ObjectType):
    node = relay.Node.Field()


class Subscription(ObjectType):
    kernel = Field(stitch(KernelRootQuery))

    def resolve_kernel(self, info):
        assert len(info.field_asts) == 1
        assert info.field_asts[0].name.value == 'kernel'

        if len(info.operation.variable_definitions) > 0:
            variable_defs = '(' + ','.join(
                    print_ast(info.operation.variable_definitions)) + ')'
        else:
            variable_defs = ''
        query = print_ast(info.field_asts[0].selection_set)
        fragments = [print_ast(x) for x in info.fragments.values()]
        complete_query = '\n'.join([
            f'''query {info.operation.name.value}{variable_defs} {query}''']
            + fragments)

        subject = rx.subjects.Subject()
        asyncio.get_running_loop().create_task(
            info.context.subscribable.subscribe(
                subject, info.context.kernel.query, complete_query,
                variables=info.variable_values))
        return subject.map(
                lambda result: stitch(KernelRootQuery)(json.loads(result)))


schema = Schema(query=ServerRootQuery, subscription=Subscription)


if __name__ == '__main__':
    print(json.dumps({'data': schema.introspect()}))
