[![Build Status](https://github.com/craigds/django-fieldsignals/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/craigds/django-fieldsignals/actions)

# Introduction

django-fieldsignals simply makes it easy to tell when the fields on your model have changed.

Often model updates are quite expensive. Sometimes the expensive operations
are very rare. This makes it tempting to put the update logic in a view,
rather than in a save() method or in a signal receiver:

```python
# A bad example. Don't do this!
def edit_poll(request, poll_id):

    # ...

    if form.cleaned_data['poll_name'] != poll.name:
        poll.update_slug(form.cleaned_data['poll_name'])
    poll.save()
```

That's a bad idea, because your model consistency is now dependent on your view.

Instead, use django-fieldsignals:

```python
from django.dispatch import receiver
from fieldsignals import pre_save_changed

@receiver(pre_save_changed, sender=Poll, fields=['name'])
def update_poll_slug(sender, instance, **kwargs):
    instance.slug = slugify(instance.name)
```


In case you want to know what changed, django-fieldsignals even tells you the old and
new values of your fields:

```python
@receiver(pre_save_changed, sender=Poll)
def print_all_field_changes(sender, instance, changed_fields, **kwargs):
    for field_name, (old, new) in changed_fields.items():
        print(f'{field_name} changed from {old} to {new}')
```

# Installation

1. This library is on PyPI so you can install it with:

```bash
    pip install django-fieldsignals
```

2. Add `"fieldsignals"` to your `INSTALLED_APPS` setting like this:

```python
INSTALLED_APPS = (
    ...
    'fieldsignals',
)
```

3. Add some signals!

# Where should my signals code live?

Field signals must be connected after the django apps are ready.
So putting signal connectors at the bottom of your models file, or other random places won't work.

The best place to connect fieldsignals is an [`AppConfig.ready()` handler](https://docs.djangoproject.com/en/dev/ref/applications/#for-application-authors).

# Notes

1. fieldsignals signals do not trigger if your fields don't change between instantiation and `save()`. That is:

```python
# This will NOT trigger post_save_changed
instance = MyModel.objects.create(field1='x')

# This will also NOT trigger post_save_changed
instance = MyModel(field1='x')
instance.save()

# But this WILL trigger post_save_changed
instance = MyModel()
instance.field1 = 'x'
instance.save()
```

If you want to also trigger your signals during creation, register your handler as a regular signal also, and check the `created` kwarg:

```python
@receiver(pre_save, sender=Poll)
@receiver(pre_save_changed, sender=Poll, fields=['name'])
def update_poll_slug(sender, instance, *, created, changed_fields=None, **kwargs):
    if created or changed_fields:
        instance.slug = slugify(instance.name)
```

2. Currently no support for `ManyToManyField` or reverse side of `ForeignKey` (one to many).
