from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.core.exceptions import AppRegistryNotReady, ValidationError
from django.db.models import signals as _signals
from django.db.models.fields.related import ForeignObjectRel
from django.dispatch import Signal

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

    from django.db import models

__all__ = ("pre_save_changed", "post_save_changed")


IMMUTABLE_TYPES_WHITELIST: tuple[type, ...] = (tuple, frozenset, float, str, int)


class ChangedSignal(Signal):
    """
    A Signal which can be connected for a list of fields (or field names).
    The given receiver is only called when one or more of the given fields has changed.
    """

    def connect(  # type: ignore[override]
        self,
        receiver: Callable[..., Any],
        sender: type[models.Model] | None = None,
        fields: list[str] | None = None,
        dispatch_uid: Hashable | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Connect a FieldSignal. Usage::

            foo.connect(func, sender=MyModel, fields=['myfield1', 'myfield2'])
        """

        if not apps.models_ready:
            # We require access to Model._meta.get_fields(), which isn't available yet.
            # (This error would be raised below anyway, but we want a more meaningful message)
            raise AppRegistryNotReady(
                "django-fieldsignals signals must be connected after the app cache is ready. "
                "Connect the signal in your AppConfig.ready() handler."
            )

        # Validate arguments

        if kwargs.get("weak", False):
            # TODO: weak refs? I'm hella confused.
            # We can't go passing our proxy receivers around as weak refs, since they're
            # defined as closures and hence don't exist by the time they're called.
            # However, we can probably make _make_proxy_receiver() create weakrefs to
            # the original receiver if required. Patches welcome
            raise NotImplementedError("This signal doesn't yet handle weak refs")

        # Check it's a class, don't check if it's a model class (useful for tests)
        if not isinstance(sender, type):
            raise ValueError("sender should be a model class")

        def is_reverse_rel(f: Any) -> bool:
            return f.many_to_many or f.one_to_many or isinstance(f, ForeignObjectRel)

        def is_virtual_field(f: Any) -> bool:
            """Virtual fields like GenericForeignKey don't have database columns."""
            return not f.concrete

        if fields is None:
            resolved_fields = sender._meta.get_fields()
            resolved_fields = [
                f
                for f in resolved_fields
                if not is_reverse_rel(f) and not is_virtual_field(f)
            ]
        else:
            resolved_fields = [f for f in sender._meta.get_fields() if f.name in set(fields)]
            for f in resolved_fields:
                if is_reverse_rel(f):
                    raise ValueError(
                        "django-fieldsignals doesn't handle reverse related fields "
                        f"({f.name} is a {f.__class__.__name__})"
                    )
                if is_virtual_field(f):
                    raise ValueError(
                        "django-fieldsignals doesn't handle virtual fields "
                        f"({f.name} is a {f.__class__.__name__})"
                    )

        if not resolved_fields:
            raise ValueError("fields must be non-empty")

        proxy_receiver = self._make_proxy_receiver(receiver, sender, resolved_fields)

        super().connect(proxy_receiver, sender=sender, weak=False, dispatch_uid=dispatch_uid)

        ### post_init : initialize the list of fields for each instance
        def post_init_closure(sender: type, instance: models.Model, **kwargs: Any) -> None:
            self.get_and_update_changed_fields(receiver, instance, resolved_fields)

        _signals.post_init.connect(
            post_init_closure,
            sender=sender,
            weak=False,
            dispatch_uid=(self, receiver),  # type: ignore[arg-type]
        )
        self.connect_source_signals(sender)

    def connect_source_signals(self, sender: type) -> None:
        """
        Connects the source signals required to trigger updates for this
        ChangedSignal.

        (post_init has already been connected during __init__)
        """
        # override in subclasses
        pass

    def _make_proxy_receiver(
        self,
        receiver: Callable[..., Any],
        sender: type,
        fields: list[Any],
    ) -> Callable[..., Any]:
        """
        Takes a receiver function and creates a closure around it that knows what fields
        to watch. The original receiver is called for an instance iff the value of
        at least one of the fields has changed since the last time it was called.
        """

        def pr(instance: Any, *args: Any, **kwargs: Any) -> None:
            changed_fields = self.get_and_update_changed_fields(receiver, instance, fields)
            if changed_fields:
                receiver(
                    *args,
                    instance=instance,
                    changed_fields=changed_fields,
                    **kwargs,
                )

        pr._original_receiver = receiver  # type: ignore[attr-defined]
        pr._fields = fields  # type: ignore[attr-defined]

        pr.__doc__ = receiver.__doc__
        pr.__name__ = receiver.__name__
        return pr

    def get_and_update_changed_fields(
        self,
        receiver: Callable[..., Any],
        instance: Any,
        fields: list[Any],
    ) -> dict[str, tuple[Any, Any]]:
        """
        Takes a receiver and a model instance, and a list of field instances.
        Gets the old and new values for each of the given fields, and stores their
        new values for next time.

        Returns a dict like this:
            {
                "fieldname1" : ("old value", "new value"),
            }
        """
        # instance._fieldsignals_originals looks like this:
        #   {
        #       (id(<signal instance>), id(<receiver>)) : {"field_name": "old value",},
        #   }
        key = (id(self), id(receiver))
        if not hasattr(instance, "_fieldsignals_originals"):
            instance._fieldsignals_originals = {}
        if key not in instance._fieldsignals_originals:
            instance._fieldsignals_originals[key] = {}
        originals = instance._fieldsignals_originals[key]
        changed_fields: dict[str, tuple[Any, Any]] = {}

        deferred_fields = instance.get_deferred_fields()

        for field in fields:
            if not field.concrete:
                # Skip virtual fields (e.g. GenericForeignKey)
                continue
            if field.attname in deferred_fields:
                continue
            # using value_from_object instead of getattr() means we don't traverse foreignkeys
            try:
                new_value = field.to_python(field.value_from_object(instance))
            except ValidationError:
                # Skip fields with invalid values (e.g., BooleanField with None)
                continue
            old_value = originals.get(field.name, None)
            if old_value != new_value:
                if not isinstance(new_value, IMMUTABLE_TYPES_WHITELIST):
                    # For mutable types, make a copy of the value before storing it.
                    # Otherwise, the 'originals' dict may well get modified elsewhere, and
                    # that's going to make change detection impossible
                    new_value = deepcopy(new_value)

                changed_fields[field.name] = (old_value, new_value)
                # now update, for next time
                originals[field.name] = new_value
        return changed_fields


class PreSaveChangedSignal(ChangedSignal):
    def _on_model_pre_save(
        self, sender: type, instance: Any = None, **kwargs: Any
    ) -> list[tuple[Callable[..., Any], Any]]:
        return self.send(sender, instance=instance)

    def connect_source_signals(self, sender: type) -> None:
        _signals.pre_save.connect(
            self._on_model_pre_save,
            sender=sender,
            dispatch_uid=id(self),  # type: ignore[arg-type]
        )


class PostSaveChangedSignal(ChangedSignal):
    def _on_model_post_save(
        self,
        sender: type,
        instance: Any = None,
        created: bool | None = None,
        using: str | None = None,
        **kwargs: Any,
    ) -> list[tuple[Callable[..., Any], Any]]:
        return self.send(sender, instance=instance, created=created, using=using)

    def connect_source_signals(self, sender: type) -> None:
        _signals.post_save.connect(
            self._on_model_post_save,
            sender=sender,
            dispatch_uid=id(self),  # type: ignore[arg-type]
        )


### API:

pre_save_changed = PreSaveChangedSignal()
post_save_changed = PostSaveChangedSignal()

# TODO other signals?
