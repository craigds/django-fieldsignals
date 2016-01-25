from contextlib import contextmanager
from collections import namedtuple
from unittest import main, TestCase

from django.db.models.signals import post_save, post_init, pre_save

from fieldsignals.signals import post_save_changed, pre_save_changed

_field = namedtuple('field', ['name'])


@contextmanager
def must_be_called(must=True):
    x = {'called': False}

    def func(*args, **kwargs):
        x['called'] = True

    try:
        yield func
    except:
        raise
    else:
        if x['called'] and not must:
            raise AssertionError("Function was called, shouldn't have been")
        elif must and not x['called']:
            raise AssertionError("Function wasn't called, should have been")


class Called(Exception):
    pass


def func(*args, **kwargs):
    raise Called


class Field(object):
    def __init__(self, name):
        self.name = name

    def value_from_object(self, instance):
        return getattr(instance, self.name)


class FakeModel(object):
    a_key = 'a value'
    another = 'something else'

    class _meta(object):
        @staticmethod
        def get_fields():
            return [
                Field('a_key'),
                Field('another'),
            ]


class TestPostSave(TestCase):
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

            obj.a_key = 'another value'
            post_save.send(instance=obj, sender=FakeModel)

    def test_post_save_with_fields_changed(self):
        with must_be_called(True) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=('a_key',))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = 'change a field that we care about'
            post_save.send(instance=obj, sender=FakeModel)

    def test_post_save_with_fields_unchanged(self):
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModel, fields=('a_key',))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = 'dont care about this field'
            post_save.send(instance=obj, sender=FakeModel)


class TestPreSave(TestCase):
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

            obj.a_key = 'another value'
            pre_save.send(instance=obj, sender=FakeModel)

    def test_pre_save_with_fields_changed(self):
        with must_be_called(True) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=('a_key',))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.a_key = 'change a field that we care about'
            pre_save.send(instance=obj, sender=FakeModel)

    def test_pre_save_with_fields_unchanged(self):
        with must_be_called(False) as func:
            pre_save_changed.connect(func, sender=FakeModel, fields=('a_key',))

            obj = FakeModel()
            post_init.send(instance=obj, sender=FakeModel)

            obj.another = 'dont care about this field'
            pre_save.send(instance=obj, sender=FakeModel)


if __name__ == '__main__':
    main()
