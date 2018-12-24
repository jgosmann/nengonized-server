from graphene import Field, List, NonNull, ObjectType, relay, Scalar


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


def _to_resolved_type(new_type):
    if isinstance(new_type, Field):
        return _to_resolved_type(new_type.type)
    elif isinstance(new_type, (List, NonNull)):
        return _to_resolved_type(new_type.of_type)
    elif isinstance(new_type, type) and issubclass(new_type, ObjectType):
        return new_type
    else:
        return lambda x: x


def _create_resolver(new_type, name):
    resolved_type = _to_resolved_type(new_type)
    if isinstance(new_type, List):
        return lambda self, info, resolved_type=resolved_type, name=name: [
                resolved_type(x) for x in self.data[name]]
    else:
        return lambda self, info, resolved_type=resolved_type, name=name: (
                resolved_type(self.data[name]))


_stitched = {}
def stitch(type_):
    assert issubclass(type_, ObjectType)

    if type_ in _stitched:
        return _stitched[type_]

    def __init__(self, data):
        self.data = data

    cls_dict = {
        '__init__': __init__
    }
    for name in dir(type_):
        attr = getattr(type_, name)
        if isinstance(attr, (Field, List, NonNull, Scalar)):
            new_type = to_stitched_type(attr)
            cls_dict[name] = new_type
            cls_dict['resolve_' + name] = _create_resolver(new_type, name)
    cls = type(ObjectType)(
            'Stitched' + type_.__name__, (ObjectType,), cls_dict,
            interfaces=type_._meta.interfaces)
    _stitched[type_] = cls
    return cls
