from graphql_relay import from_global_id
from graphene import Field, ID, List, NonNull, ObjectType, relay, Scalar


_stitched = {}

def to_stitched_type(type_):
    if isinstance(type_, Field):
        return Field(to_stitched_type(type_.type))
    elif isinstance(type_, (List, NonNull)):
        return type_.__class__(to_stitched_type(type_.of_type))
    elif isinstance(type_, Scalar):
        return type_
    elif issubclass(type_, Scalar):
        return type_
    else:
        return stitch(type_)


def _cast(new_type, obj):
    if isinstance(new_type, NonNull):
        assert obj is not None
        return _cast(new_type.of_type, obj)
    elif obj is None:
        return None
    elif isinstance(new_type, List):
        return [_cast(new_type.of_type, x) for x in obj]
    elif isinstance(new_type, Field):
        return _cast(new_type.type, obj)
    elif isinstance(new_type, type) and issubclass(new_type, ObjectType):
        return new_type(obj)
    elif isinstance(new_type, ID):
        return from_global_id(obj)[1]
    else:
        return obj


def _create_resolver(new_type, name):
    return lambda self, info, new_type=new_type, name=name: (
        _cast(new_type, self.data[name]))


class StitchedRelayNodeField(relay.node.NodeField):
    def __init__(self, name, *args, **kwargs):
        super().__init__(relay.node.Node, *args, **kwargs)
        self.name = name

    def get_resolver(self, parent_resolver):
        return self.stitched_resolver

    def stitched_resolver(self, obj, info, id):
        type_, local_id = from_global_id(id)
        graphene_type = info.schema.get_type(type_).graphene_type
        return graphene_type(obj.data[self.name])


_stitched = {}
def stitch(type_):
    assert issubclass(type_, ObjectType), f"Expected ObjectType, got {type_}."

    if type_ in _stitched:
        return _stitched[type_]

    def __init__(self, data):
        self.data = data

    _stitched[type_] = lambda type_=type_: _stitched[type_]
    cls_dict = {
        '__init__': __init__
    }
    for name in dir(type_):
        attr = getattr(type_, name)
        if isinstance(attr, relay.node.NodeField):
            cls_dict[name] = StitchedRelayNodeField(name)
        elif isinstance(attr, (Field, List, NonNull, Scalar)):
            new_type = to_stitched_type(attr)
            cls_dict[name] = new_type
            cls_dict['resolve_' + name] = _create_resolver(new_type, name)
    if relay.Node in type_._meta.interfaces:
        cls_dict['resolve_id'] = _create_resolver(ID(), 'id')
    cls = type(ObjectType)(
            type_.__name__, (ObjectType,), cls_dict,
            interfaces=type_._meta.interfaces)
    _stitched[type_] = cls
    return cls
