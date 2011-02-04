
__all__ = ('post_fields_changed',)

from django.db.models.fields import Field
from django.db.models import Model
from django.db.models import signals as _signals
from django.dispatch import Signal


class ChangedFieldsSignal(Signal):
    """
    A Signal which can be connected for a list of fields (or field names).
    The given receiver is only called when one or more of the given fields has changed.
    """
    
    def connect(self, receiver, sender=None, fields=None, weak=True, dispatch_uid=None, **kwargs):
        """
        Connect a FieldSignal. Usage::
        
            foo.connect(func, sender=MyModel, fields=['myfield1', 'myfield2'])
        """
        
        # Validate arguments
        if not issubclass(sender, Model):
            raise ValueError("sender should be a model class")
        
        if fields is None:
            fields = sender._meta.fields[:]
        else:
            fields = [sender._meta.get_field(f) for f in fields]
        
        if not fields:
            raise ValueError("fields must be non-empty")
        
        proxy_receiver = self._make_proxy_receiver(receiver, sender, fields)
        
        super(ChangedFieldsSignal, self).connect(proxy_receiver, sender=sender, weak=weak, dispatch_uid=dispatch_uid)
        
        ### post_init : initialize the list of fields for each instance
        def post_init_closure(sender, instance, **kwargs):
            self.get_and_update_changed_fields(receiver, instance, fields)
        _signals.post_init.connect(post_init_closure, sender=sender, dispatch_uid=(self, receiver))
        self.connect_source_signals(sender)
    
    def connect_source_signals(self, sender):
        """
        Connects the source signals required to trigger updates for this
        ChangedFieldsSignal.
        
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
                receiver(instance, changed_fields=changed_fields, *args, **kwargs)
        
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
        #       (<signal instance>, <receiver>) : {<field instance>: "old value",},
        #   }
        if not hasattr(instance, '_fieldsignals_originals'):
            sender._fieldsignals_originals = {}
        originals = sender._fieldsignals_originals[(self, receiver)]
        changed_fields = {}
        
        for field in fields:
            # using value_from_object instead of getattr() means we don't traverse foreignkeys
            new_value = field.value_from_object(instance)
            old_value = originals.get(field, None)
            if old_value != new_value:
                changed_fields[field] = (old_value, new_value)
            # now update, for next time
            originals[field] = new_value
        return changed_fields    


### API:

class PostSaveChangedFieldsSignal(ChangedFieldsSignal):
    def _on_model_post_save(self, sender, instance=None, created=None, using=None, **kwargs):
        # changed_fields=[...] is added by the proxy receiver for each receiver
        return self.send_robust(sender, instance=instance, created=created, using=using)
    
    def connect_source_signals(self, sender):
        _signals.post_save.connect(self._on_model_post_save, sender=sender, dispatch_uid=id(self))

post_fields_changed = PostSaveChangedFieldsSignal(providing_args=["instance", "changed_fields", "created", "using"])

#TODO other signals


