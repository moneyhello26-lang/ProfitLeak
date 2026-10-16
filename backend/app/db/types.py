"""Exact fixed point values on SQLite and NUMERIC on optional PostgreSQL."""

from datetime import timezone
from decimal import Decimal, localcontext

from sqlalchemy import BigInteger, DateTime, Numeric
from sqlalchemy.types import TypeDecorator


class ExactDecimal(TypeDecorator):
    impl = Numeric
    cache_ok = True

    def __init__(self, precision=18, scale=2):
        self.precision = precision
        self.scale = scale
        super().__init__(precision=precision, scale=scale)

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(BigInteger())
        return dialect.type_descriptor(Numeric(self.precision, self.scale))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = Decimal(str(value))
        if not value.is_finite():
            raise ValueError("Financial values must be finite")
        with localcontext() as context:
            context.prec = 64
            scaled = value * 10**self.scale
            if scaled != scaled.to_integral_value() or abs(scaled) >= 10**self.precision:
                raise ValueError("Financial value exceeds its fixed point precision")
        return int(scaled) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        with localcontext() as context:
            context.prec = 64
            number = Decimal(value).scaleb(-self.scale) if dialect.name == "sqlite" else value
            return number.quantize(Decimal(1).scaleb(-self.scale))


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc) if value is not None else None
