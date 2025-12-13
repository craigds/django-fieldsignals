# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

django-fieldsignals provides Django signals that fire when specific model fields change. It exposes two signals: `pre_save_changed` and `post_save_changed`, which work like Django's built-in `pre_save`/`post_save` but only trigger when specified fields have actually changed.

## Commands

```bash
# Run tests (requires Django to be installed)
pytest -v

# Run tests across all supported Python/Django versions
tox

# Run a single test
pytest -v fieldsignals/tests/test_signals.py::TestPreSave::test_pre_save_changed

# Lint
ruff check .

# Type check
tox -e mypy
```

## Architecture

The library is small:
- `fieldsignals/signals.py` - Core implementation with `ChangedSignal` base class and `PreSaveChangedSignal`/`PostSaveChangedSignal` subclasses
- `fieldsignals/__init__.py` - Exports `pre_save_changed` and `post_save_changed` signal instances

Key design points:
- Signals must be connected after the Django app registry is ready (in `AppConfig.ready()`)
- Field change tracking stores original values on the model instance in `_fieldsignals_originals`
- Deferred fields are excluded from change detection
- No support for `ManyToManyField` or reverse FK relations
