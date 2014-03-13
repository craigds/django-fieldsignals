
__all__ = ('pre_save_changed', 'post_save_changed',)

from django.db.models import Model
from django.db.models import signals as _signals
from django.dispatch import Signal


class ChangedSignal(Signal):
    """
    A Signal which can be connected for a list of fields (or field names).
    The given receiver is only called when one or more of the given fields has changed.
    """

    def connect(self, receiver, sender=None, fields=None, dispatch_uid=None, **kwargs):
        """
        Connect a FieldSignal. Usage::

            foo.connect(func, sender=MyModel, fields=['myfield1', 'myfield2'])
        """

        # Validate arguments

        if kwargs.get('weak', False):
            # TODO: weak refs? I'm hella confused.
            # We can't go passing our proxy receivers around as weak refs, since they're
            # defined as closures and hence don't exist by the time they're called.
            # However, we can probably make _make_proxy_receiver() create weakrefs to
            # the original receiver if required. Patches welcome
            raise NotImplementedError("This signal doesn't yet handle weak refs")

        if not issubclass(sender, Model):
            raise ValueError("sender should be a model class")

        if fields is None:
            fields = sender._meta.fields[:]
        else:
            fields = [sender._meta.get_field(f) for f in fields]

        if not fields:
            raise ValueError("fields must be non-empty")

        proxy_receiver = self._make_proxy_receiver(receiver, sender, fields)

        super(ChangedSignal, self).connect(proxy_receiver, sender=sender, weak=False, dispatch_uid=dispatch_uid)

        ### post_init : initialize the list of fields for each instance
        def post_init_closure(sender, instance, **kwargs):
            self.get_and_update_changed_fields(receiver, instance, fields)
        _signals.post_init.connect(post_init_closure, sender=sender, weak=False, dispatch_uid=(self, receiver))
        self.connect_source_signals(sender)

    def connect_source_signals(self, sender):
        """
        Connects the source signals required to trigger updates for this
        ChangedSignal.

        (post_init has already been connected during __init__)
        """
        # override in subclasses
        pass

    def _make_proxy_receiver(self, receiver, sender, fields):
        """
        Takes a receiver function and creates a closure around it that knows what fields
        to watch. The original receiver is called for an instance iff the value of
        at least one of the fields has changed since the last time it was called.
        """
        def pr(instance, *args, **kwargs):
            changed_fields = self.get_and_update_changed_fields(receiver, instance, fields)
            if changed_fields:
                receiver(instance=instance, changed_fields=changed_fields, *args, **kwargs)

        pr._original_receiver = receiver
        pr._fields = fields

        pr.__doc__ = receiver.__doc__
        pr.__name__ = receiver.__name__
        return pr

    def get_and_update_changed_fields(self, receiver, instance, fields):
        """
        Takes a receiver and a model instance, and a list of field instances.
        Gets the old and new values for each of the given fields, and stores their
        new values for next time.

        Returns a dict like this:
            {
                <field1> : ("old value", "new value"),
            }
        """
        # instance._fieldsignals_originals looks like this:
        #   {
        #       (id(<signal instance>), id(<receiver>)) : {"field_name": "old value",},
        #   }
        key = (id(self), id(receiver))
        if not hasattr(instance, '_fieldsignals_originals'):
            instance._fieldsignals_originals = {}
        if not key in instance._fieldsignals_originals:
            instance._fieldsignals_originals[key] = {}
        originals = instance._fieldsignals_originals[key]
        changed_fields = {}

        for field in fields:
            # using value_from_object instead of getattr() means we don't traverse foreignkeys
            new_value = field.value_from_object(instance)
            old_value = originals.get(field.name, None)
            if old_value != new_value:
                changed_fields[field] = (old_value, new_value)
            # now update, for next time
            originals[field.name] = new_value
        return changed_fields


class PreSaveChangedSignal(ChangedSignal):
    def _on_model_pre_save(self, sender, instance=None, **kwargs):
        return self.send(sender, instance=instance)

    def connect_source_signals(self, sender):
        _signals.pre_save.connect(self._on_model_pre_save, sender=sender, dispatch_uid=id(self))


class PostSaveChangedSignal(ChangedSignal):
    def _on_model_post_save(self, sender, instance=None, created=None, using=None, **kwargs):
        return self.send(sender, instance=instance, created=created, using=using)

    def connect_source_signals(self, sender):
        _signals.post_save.connect(self._on_model_post_save, sender=sender, dispatch_uid=id(self))


### API:

pre_save_changed = PreSaveChangedSignal(providing_args=["instance", "changed_fields"])
post_save_changed = PostSaveChangedSignal(providing_args=["instance", "changed_fields", "created", "using"])

#TODO other signals?
