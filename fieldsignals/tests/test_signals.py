from contextlib import contextmanager
from collections import namedtuple
from unittest import main, TestCase

from django.db.models.fields.related import OneToOneRel
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
    def __init__(self, name, m2m=False):
        self.name = name
        self.many_to_many = m2m
        self.one_to_many = False

    def value_from_object(self, instance):
        return getattr(instance, self.name)


class FakeModel(object):
    a_key = 'a value'
    another = 'something else'
    m2m = []

    class _meta(object):
        @staticmethod
        def get_fields():
            return [
                Field('a_key'),
                Field('another'),
                Field('m2m', m2m=True),
            ]


class MockOneToOneRel(OneToOneRel):
    def __init__(self, name):
        self.name = name
        self.many_to_many = False
        self.one_to_many = False


class FakeModelWithOneToOne(object):
    f = 'a value'
    o2o = 1

    class _meta(object):
        @staticmethod
        def get_fields():
            return [
                Field('f'),
                MockOneToOneRel('o2o')
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

    def test_post_save_with_m2m_fields_error(self):
        with must_be_called(False) as func:
            with self.assertRaises(ValueError):
                post_save_changed.connect(func, sender=FakeModel, fields=('m2m',))

    def test_with_one_to_one_rel_field_error(self):
        with must_be_called(False) as func:
            with self.assertRaises(ValueError):
                post_save_changed.connect(func, sender=FakeModelWithOneToOne, fields=('o2o', 'f'))

    def test_with_one_to_one_rel_excluded(self):
        with must_be_called(False) as func:
            post_save_changed.connect(func, sender=FakeModelWithOneToOne)


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

    def test_pre_save_with_m2m_fields_error(self):
        with must_be_called(False) as func:
            with self.assertRaises(ValueError):
                pre_save_changed.connect(func, sender=FakeModel, fields=('m2m',))


if __name__ == '__main__':
    main()
