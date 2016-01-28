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
    from fieldsignals import pre_save_changed

    def update_poll_slug(sender, instance, **kwargs):
        instance.slug = slugify(instance.name)

    pre_save_changed.connect(update_poll_slug, sender=Poll, fields=['name'])
```


In case you want to know what changed, django-fieldsignals even tells you the old and
new values of your fields:

```python
    from fieldsignals import pre_save_changed

    def print_all_field_changes(sender, instance, changed_fields=None, **kwargs):
        for field, (old, new) in changed_fields.items():
            print "%s changed from %s to %s" % (field.name, old, new)

    pre_save_changed.connect(print_all_field_changes, sender=Poll)
```

# Installation

1. This library is on PyPI so you can install it with:

```bash
    pip install django-fieldsignals
```

or from github:

```bash
    pip install 'git+https://github.com/craigds/django-fieldsignals.git#egg=django-fieldsignals'
```

2. Add `"fieldsignals"` to your `INSTALLED_APPS` setting like this:

```python
    INSTALLED_APPS = (
        ...
        'fieldsignals',
    )
```

# Notes

* Currently no support for `ManyToManyField` or reverse side of `ForeignKey` (one to many).
* If you've enjoyed this project and want to help me spend more time on open source, flattr me! [![Flattr me](http://api.flattr.com/button/flattr-badge-large.png)](https://flattr.com/submit/auto?user_id=craigds&url=https://github.com/craigds/django-fieldsignals/&title=django-fieldsignals&language=en_GB&tags=django,python,github&category=software)
