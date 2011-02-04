
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
        
        # sender._fieldsignals_fields looks like this:
        #   {
        #       <signal instance> : [field1, field2...],
        #   }
        
        if not hasattr(sender, '_fieldsignals_fields'):
            sender._fieldsignals_fields = {}
        
        if self in sender._fieldsignals_fields:
            # TODO: find a way to fix this without data from multiple signals conflicting with each other
            raise ValueError("This signal has already been registered for this model, and can't be registered twice.")
        
        sender._fieldsignals_fields[self] = fields
        
        super(ChangedFieldsSignal, self).connect(receiver, sender=sender, weak=weak, dispatch_uid=dispatch_uid)


### API:

post_fields_changed = ChangedFieldsSignal(providing_args=["instance", "changed_fields", "created", "using"])

#TODO other signals






### Utilities

def update_watched_fields(sender, instance, signal_instance):
    # see comment explaining sender._fieldsignals_fields in ChangedFieldsSignal.connect()
    
    watched_fields = sender._fieldsignals_fields.get(signal_instance, [])
    if watched_fields:
        if not hasattr(instance, '_fieldsignals_originals'):
            instance._fieldsignals_originals = {}
        
        instance._fieldsignals_originals[signal_instance] = originals = {}
        
        for field in watched_fields:
            # value_from_object() returns a field's *raw* value (i.e. don't try to look up foreignkeys etc)
            originals[field.name] = field.value_from_object(instance)

def get_changed_fields(sender, instance, signal_instance):
    # see comment explaining sender._fieldsignals_fields in ChangedFieldsSignal.connect()
    changed_fields = {}
    originals = getattr(instance, '_fieldsignals_originals', {}).get(signal_instance, {})
    if originals:
        for field, old_value in originals.items():
            new_value = field.value_from_object(instance)
            if old_value != new_value:
                changed_fields[field.name] = (old_value, new_value)
    return changed_fields


### SOURCE signals - set up signal receivers to make stuff work

# post_init : to keep track of the original versions of fields.
def post_model_init(sender, instance, **kwargs):
    watched_fields = getattr(sender, '_fieldsignals_fields', {})
    for signal_instance in watched_fields.keys():
        update_watched_fields(sender, instance, signal_instance)
_signals.post_init.connect(post_model_init)

# post_save : to trigger `post_fields_changed`
def on_model_post_save(sender, instance, **kwargs):
    changed_fields = get_changed_fields(sender, instance, post_fields_changed)
    if changed_fields:
        post_fields_changed.send(sender=sender, instance=instance, changed_fields=changed_fields, **kwargs)
        update_watched_fields(sender, instance)
_signals.post_save.connect(on_model_post_save)
