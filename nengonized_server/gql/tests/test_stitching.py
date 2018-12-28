from graphene import Field, Interface, List, NonNull, ObjectType, String
import pytest

from nengonized_server.gql.stitching import stitch, to_stitched_type


def create_obj_type_mock(field_type, **kwargs):
    class ObjTypeMock(ObjectType, **kwargs):
        field = field_type

        def __init__(self):
            raise AssertionError("Original __init__ should not be called.")

        def resolve_field(self, info):
            raise AssertionError("Original resolver should not be called.")
    return ObjTypeMock


DummyObjType = create_obj_type_mock(String())

def assert_field_types_are_equal(actual, expected):
    if isinstance(expected, type):
        assert actual is expected
    else:
        assert type(actual) == type(expected)
        if hasattr(expected, 'type'):
            assert_field_types_are_equal(actual.type, expected.type)
        elif hasattr(expected, 'of_type'):
            assert_field_types_are_equal(actual.of_type, expected.of_type)


@pytest.mark.parametrize('input_type,expected', [
    (Field(DummyObjType), Field(stitch(DummyObjType))),
    (List(DummyObjType), List(stitch(DummyObjType))),
    (NonNull(DummyObjType), NonNull(stitch(DummyObjType))),
    (NonNull(List(NonNull(DummyObjType))),
        NonNull(List(NonNull(stitch(DummyObjType))))),
    (String(), String())
])
def test_to_stitched_type(input_type, expected):
    assert_field_types_are_equal(to_stitched_type(input_type), expected)


class TestStitch(object):
    def test_stitching_converts_to_dict_initializable_type(self):
        OrigType = create_obj_type_mock(String())
        data = {'field': 'value'}
        stitched = stitch(OrigType)(data)

        assert stitched.resolve_field(None) == 'value'

    def test_handles_non_null(self):
        OrigType = create_obj_type_mock(NonNull(String))
        data = {'field': 'value'}
        stitched = stitch(OrigType)(data)

        assert stitched.resolve_field(None) == 'value'

    def test_handles_list(self):
        OrigType = create_obj_type_mock(List(String))
        data = {'field': ['foo', 'bar', 'baz']}
        stitched = stitch(OrigType)(data)

        assert stitched.resolve_field(None) == data['field']

    def test_handles_non_null_list_of_non_null(self):
        OrigType = create_obj_type_mock(NonNull(List(NonNull(String))))
        data = {'field': ['foo', 'bar', 'baz']}
        stitched = stitch(OrigType)(data)

        assert stitched.resolve_field(None) == data['field']

    def test_handles_nested_types(self):
        InnerType = create_obj_type_mock(String())
        OuterType = create_obj_type_mock(Field(InnerType))
        data = {'field': {'field': 'innerValue'}}
        stitched = stitch(OuterType)(data)

        assert stitched.resolve_field(None).resolve_field(None) == 'innerValue'

    def test_handles_non_null_list_of_non_null_nested_type(self):
        InnerType = create_obj_type_mock(Field(String))
        OuterType = create_obj_type_mock(NonNull(List(NonNull(InnerType))))
        data = {'field': [{'field': 'a'}, {'field': 'b'}]}
        stitched = stitch(OuterType)(data)

        outer = stitched.resolve_field(None)
        print(outer)
        assert [x.resolve_field(None) for x in outer] == ['a', 'b']

    def test_handles_interfaces(self):
        class TestInterface(Interface):
            field = String()
        OrigType = create_obj_type_mock(String(), interfaces=[TestInterface])

        assert stitch(OrigType)._meta.interfaces == [TestInterface]
