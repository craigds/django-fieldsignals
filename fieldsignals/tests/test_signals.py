from __future__ import annotations

import datetime
from collections import namedtuple
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from django.apps import apps
from django.core.exceptions import AppRegistryNotReady, ValidationError
from django.db.models.fields.related import OneToOneRel
from django.db.models.signals import post_init, post_save, pre_save
from django.utils.dateparse import parse_datetime

from fieldsignals.signals import post_save_changed, pre_save_changed

_field = namedtuple("field", ["name"])


@contextmanager
def must_be_called(must: bool = True) -> Generator[Any, None, None]:
    x = {"called": False}

    def func(*args: Any, **kwargs: Any) -> None:
        x["called"] = True
        func.args = args  # type: ignore[attr-defined]
        func.kwargs = kwargs  # type: ignore[attr-defined]

    func.args = None  # type: ignore[attr-defined]
    func.kwargs = None  # type: ignore[attr-defined]

    yield func

    if x["called"] and not must:
        raise AssertionError("Function was called, shouldn't have been")
    elif must and not x["called"]:
        raise AssertionError("Function wasn't called, should have been")


class Called(Exception):
    pass


def func(*args: Any, **kwargs: Any) -> None:
    raise Called


class Field:
    def __init__(self, name: str, m2m: bool = False) -> None:
        self.name = name
        self.attname = name
        self.many_to_many = m2m
        self.one_to_many = False
        self.concrete = True

    def value_from_object(self, instance: Any) -> Any:
        return getattr(instance, self.name)

    def to_python(self, value: Any) -> Any:
        return value


class DateTimeField(Field):
    def to_python(self, value: Any) -> datetime.datetime | None:
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value
        return parse_datetime(value)


class BooleanField(Field):
    def to_python(self, value: Any) -> bool:
        if value is None:
            raise ValidationError('"None" value must be either True or False.')
        return bool(value)


class FakeModel:
    a_key = "a value"
    another = "something else"
    m2m: list[Any] = []
    a_datetime: datetime.datetime | None = None

    class _meta:
        @staticmethod
        def get_fields() -> list[Field]:
            return [
                Field("a_key"),
                Field("another"),
                Field("m2m", m2m=True),
                DateTimeField("a_datetime"),
            ]

    def get_deferred_fields(self) -> set[str]:
        return set()


class DeferredModel:
    a = 1

    class _meta:
        @staticmethod
        def get_fields() -> list[Field]:
            return [
                Field("a"),
                Field("b"),
            ]

    def get_deferred_fields(self) -> set[str]:
        return {"b"}


class BooleanFieldModel:
    is_active: bool | None = None
    name: str = "test"

    class _meta:
        @staticmethod
        def get_fields() -> list[Field]:
            return [
                BooleanField("is_active"),
                Field("name"),
            ]

    def get_deferred_fields(self) -> set[str]:
        return set()


class MockOneToOneRel(OneToOneRel):
    def __init__(self, name: str) -> None:
        self.name = name
        self.many_to_many = False
        self.one_to_many = False


class FakeModelWithOneToOne:
    f = "a value"
    o2o = 1

    class _meta:
        @staticmethod
        def get_fields() -> list[Field | MockOneToOneRel]:
            return [Field("f"), MockOneToOneRel("o2o")]


class VirtualField:
    """Mock GenericForeignKey - virtual field with no database column."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.many_to_many = False
        self.one_to_many = False
        self.concrete = False


class FakeModelWithVirtualField:
    f = "a value"
    gfk = None

    class _meta:
        @staticmethod
        def get_fields() -> list[Field | VirtualField]:
            return [Field("f"), VirtualField("gfk")]

    def get_deferred_fields(self) -> set[str]:
        return set()


class TestGeneral:
    @pytest.fixture(autouse=True)
    def ready(self) -> None:
        apps.models_ready = True

    def test_m2m_fields_error(self) -> None:
        with must_be_called(False) as func:
            with pytest.raises(ValueError):
                post_save_changed.connect(func, sender=FakeModel, fields=["m2m"])

    def test_one_to_one_rel_field_error(self) -> None:
        with must_be_called(False) as func:
            with pytest.raises(ValueError):
                post_save_changed.connect(func, sender=FakeModelWithOneToOne, fields=["o2o", "f"])

    def test_one_to_one_rel_excluded(self) -> None:
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModelWithOneToOne)

    def test_app_cache_not_ready(self) -> None:
        apps.models_ready = False
        with pytest.raises(AppRegistryNotReady):
            post_save_changed.connect(func, sender=FakeModel)

    def test_compare_after_to_python(self) -> None:
        """
        Field values (e.g. datetimes) are equal even if set via string.
        """
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=["a_datetime"])

            obj = FakeModel()
            obj.a_datetime = "2017-01-01T00:00:00.000000Z"  # type: ignore[assignment]
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_datetime = datetime.datetime(2017, 1, 1, 0, 0, 0, 0, datetime.timezone.utc)
            pre_save.send(instance=obj, sender=FakeModel)

    def test_deferred_fields(self) -> None:
        pre_save_changed.connect(func, sender=DeferredModel)

        obj = DeferredModel()
        post_init.send(instance=obj, sender=DeferredModel)

        assert list(obj._fieldsignals_originals.values()) == [{"a": 1}]

    def test_boolean_field_with_none(self) -> None:
        """
        BooleanField.to_python(None) raises ValidationError.
        Ensure post_init doesn't crash when field value is None.
        """
        with must_be_called(False) as test_func:
            pre_save_changed.connect(test_func, sender=BooleanFieldModel)

            obj = BooleanFieldModel()
            # Should not raise ValidationError
            post_init.send(instance=obj, sender=BooleanFieldModel)

            # Only 'name' field should be tracked (is_active skipped due to ValidationError)
            assert list(obj._fieldsignals_originals.values()) == [{"name": "test"}]

    def test_boolean_field_transition_to_valid(self) -> None:
        """
        When a BooleanField transitions from invalid (None) to valid (True/False),
        the signal should fire with old_value=None.
        """
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=BooleanFieldModel, fields=["is_active"])

            obj = BooleanFieldModel()
            post_init.send(instance=obj, sender=BooleanFieldModel)

            obj.is_active = True
            pre_save.send(instance=obj, sender=BooleanFieldModel)

        assert func.kwargs["changed_fields"] == {"is_active": (None, True)}

    def test_virtual_field_excluded(self) -> None:
        """Virtual fields like GenericForeignKey are auto-skipped."""
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModelWithVirtualField)

            obj = FakeModelWithVirtualField()
            post_init.send(instance=obj, sender=FakeModelWithVirtualField)
            post_save.send(instance=obj, sender=FakeModelWithVirtualField)

    def test_virtual_field_error(self) -> None:
        """Explicitly requesting a virtual field raises clear error."""
        with must_be_called(False) as func:
            with pytest.raises(
                ValueError, match="doesn't handle virtual fields.*gfk.*VirtualField"
            ):
                post_save_changed.connect(func, sender=FakeModelWithVirtualField, fields=["gfk"])


class TestPostSave:
    @pytest.fixture(autouse=True)
    def ready(self) -> None:
        apps.models_ready = True

    def test_post_save_unchanged(self) -> None:
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)
            post_save.send(instance=obj, sender=FakeModel)

    def test_post_save_changed(self) -> None:
        with must_be_called(True) as func:
            post_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "another value"
            post_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {"a_key": ("a value", "another value")}

    def test_post_save_with_fields_changed(self) -> None:
        with must_be_called(True) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=["a_key"])

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "change a field that we care about"
            post_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {
            "a_key": ("a value", "change a field that we care about")
        }

    def test_post_save_with_fields_unchanged(self) -> None:
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=["a_key"])

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = "dont care about this field"
            post_save.send(instance=obj, sender=FakeModel)


class TestPreSave:
    @pytest.fixture(autouse=True)
    def unready(self) -> None:
        apps.models_ready = True

    def test_pre_save_unchanged(self) -> None:
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)
            pre_save.send(instance=obj, sender=FakeModel)

    def test_pre_save_changed(self) -> None:
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=FakeModel)

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "another value"
            pre_save.send(instance=obj, sender=FakeModel)

        assert func.kwargs["changed_fields"] == {"a_key": ("a value", "another value")}

    def test_pre_save_with_fields_changed(self) -> None:
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=["a_key"])

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = "change a field that we care about"
            pre_save.send(instance=obj, sender=FakeModel)
        assert func.kwargs["changed_fields"] == {
            "a_key": ("a value", "change a field that we care about")
        }

    def test_pre_save_with_fields_unchanged(self) -> None:
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=["a_key"])

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = "dont care about this field"
            pre_save.send(instance=obj, sender=FakeModel)
