import datetime
from contextlib import contextmanager
from collections import namedtuple

import pytest

from django.apps import apps
from django.core.exceptions import AppRegistryNotReady
from django.db.models.fields.related import OneToOneRel
from django.db.models.signals import post_save, post_init, pre_save
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc

from fieldsignals.signals import post_save_changed, pre_save_changed

_field = namedtuple("field", ["name"])


@contextmanager
def must_be_called(must=True):
    x = {"called": False}

    def func(*args, **kwargs):
        x["called"] = True
        func.args = args
        func.kwargs = kwargs

    func.args = None
    func.kwargs = None

    yield func

    if x["called"] and not must:
        raise AssertionError("Function was called, shouldn't have been")
    elif must and not x["called"]:
        raise AssertionError("Function wasn't called, should have been")


class Called(Exception):
    pass


def func(*args, **kwargs):
    raise Called


class Field(object):
    def __init__(self, name, m2m=False):
        self.name = name
        self.attname = name
        self.many_to_many = m2m
        self.one_to_many = False

    def value_from_object(self, instance):
        return getattr(instance, self.name)

    def to_python(self, value):
        return value


class DateTimeField(Field):
    def to_python(self, value):
        # approximate a datetime field
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value

        return parse_datetime(value)


class FakeModel(object):
    a_key = "a value"
    another = "something else"
    m2m = []
    a_datetime = None

    class _meta(object):
        @staticmethod
        def get_fields():
            return [
                Field("a_key"),
                Field("another"),
                Field("m2m", m2m=True),
                DateTimeField("a_datetime"),
            ]

    def get_deferred_fields(self):
        return set()


class DeferredModel(object):
    a = 1

    class _meta(object):
        @staticmethod
        def get_fields():
            return [
                Field("a"),
                Field("b"),
            ]

    def get_deferred_fields(self):
        return {"b"}


class MockOneToOneRel(OneToOneRel):
    def __init__(self, name):
        self.name = name
        self.many_to_many = False
        self.one_to_many = False


class FakeModelWithOneToOne(object):
    f = "a value"
    o2o = 1

    class _meta(object):
        @staticmethod
        def get_fields():
            return [Field("f"), MockOneToOneRel("o2o")]


class TestGeneral(object):
    @pytest.fixture(autouse=True)
    def ready(self):
        apps.models_ready = True

    def test_m2m_fields_error(self):
        with must_be_called(False) as func:
            with pytest.raises(ValueError):
                post_save_changed.connect(func, sender=FakeModel, fields=("m2m",))

    def test_one_to_one_rel_field_error(self):
        with must_be_called(False) as func:
            with pytest.raises(ValueError):
                post_save_changed.connect(
                    func, sender=FakeModelWithOneToOne, fields=("o2o", "f")
                )

    def test_one_to_one_rel_excluded(self):
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModelWithOneToOne)

    def test_app_cache_not_ready(self):
        apps.models_ready = False
        with pytest.raises(AppRegistryNotReady):
            post_save_changed.connect(func, sender=FakeModel)

    def test_compare_after_to_python(self):
        """
        Field values (e.g. datetimes) are equal even if set via string.
        Ensures that to_python() is called prior to comparison between old & new values.
        """
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=("a_datetime",))

            obj = FakeModel()
            obj.a_datetime = "2017-01-01T00:00:00.000000Z"
            post_init.send(instance=obj, sender=FakeModel)

            # This is identical to the above, even though the type is different,
            # so don't call the signal
            obj.a_datetime = datetime.datetime(2017, 1, 1, 0, 0, 0, 0, utc)
            pre_save.send(instance=obj, sender=FakeModel)

    def test_deferred_fields(self):
        pre_save_changed.connect(func, sender=DeferredModel)

        obj = DeferredModel()
        post_init.send(instance=obj, sender=DeferredModel)

        assert list(obj._fieldsignals_originals.values()) == [{"a": 1}]


class TestPostSave(object):
    @pytest.fixture(autouse=True)
    def ready(self):
        apps.models_ready = True

    def test_post_save_unchanged(self):
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)
            # This *doesn't* call post_save_changed, because we haven't changed anything.
            post_save.send(instance=obj, sender=FakeModel)

    def test_post_save_changed(self):
        with must_be_called(True) as func:
            post_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "another value"
            post_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {"a_key": ("a value", "another value")}

    def test_post_save_with_fields_changed(self):
        with must_be_called(True) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=("a_key",))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "change a field that we care about"
            post_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {
            "a_key": ("a value", "change a field that we care about")
        }

    def test_post_save_with_fields_unchanged(self):
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=("a_key",))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = "dont care about this field"
            post_save.send(instance=obj, sender=FakeModel)


class TestPreSave(object):
    @pytest.fixture(autouse=True)
    def unready(self):
        apps.models_ready = True

    def test_pre_save_unchanged(self):
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()

            # post_init sets list of initial values
            post_init.send(instance=obj, sender=FakeModel)
            # This *doesn't* call pre_save_changed, because we haven't changed anything.
            pre_save.send(instance=obj, sender=FakeModel)

    def test_pre_save_changed(self):
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()

            # post_init sets list of initial values
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "another value"
            pre_save.send(instance=obj, sender=FakeModel)

        assert func.kwargs["changed_fields"] == {"a_key": ("a value", "another value")}

    def test_pre_save_with_fields_changed(self):
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=("a_key",))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "change a field that we care about"
            pre_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {
            "a_key": ("a value", "change a field that we care about")
        }

    def test_pre_save_with_fields_unchanged(self):
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=("a_key",))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = "dont care about this field"
            pre_save.send(instance=obj, sender=FakeModel)
