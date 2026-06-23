"""Portable column types.

Production runs on PostgreSQL (JSONB, native arrays); the test suite runs on
SQLite. These helpers use the Postgres type with a generic JSON variant on other
dialects so the same models create cleanly in both environments.
"""
from __future__ import annotations

import enum

from sqlalchemy import JSON, String, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB


def jsonb():
    """JSONB on PostgreSQL, generic JSON elsewhere."""
    return PG_JSONB().with_variant(JSON(), "sqlite")


def array(item_type):
    """Native ARRAY on PostgreSQL, JSON-encoded list elsewhere."""
    return PG_ARRAY(item_type).with_variant(JSON(), "sqlite")


class EnumStr(TypeDecorator):
    """Store a Python ``str`` enum as VARCHAR and return the enum member on read.

    Avoids native DB enum types (portable across PostgreSQL and SQLite) while
    guaranteeing that attribute reads after a DB round-trip yield the enum, not a
    bare string — so ``obj.field.value`` works consistently everywhere.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[enum.Enum], length: int = 32, **kw):
        self._enum = enum_cls
        super().__init__(length=length, **kw)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self._enum):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._enum(value)
