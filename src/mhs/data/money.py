"""Convert money fields between ingest dollars and stored integer cents."""

from decimal import ROUND_HALF_UP, Decimal

# Keys whose values are money anywhere in a record (including nested lines and items).
MONEY_KEYS = {
    "amount", "billed", "allowed", "adjustment", "insurer_paid", "additional_savings", "deductible",
    "copay", "coinsurance", "not_covered", "patient_responsibility", "balance_due", "billed_charge",
    "insurance_paid", "rate", "patient_amount", "patient_paid", "balance", "charge", "total",
    "account_balance_after",
}
MONEY_MAP_KEYS = {"copays"}  # objects whose values are all money


def cents(value) -> int | None:
    if value is None:
        return None
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def dollars(value: int | None):
    if value is None:
        return None
    d = Decimal(value) / 100
    return int(d) if d == d.to_integral_value() else float(d)


def _walk(obj, fn):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in MONEY_KEYS and (v is None or isinstance(v, (int, float))):
                out[k] = fn(v)
            elif k in MONEY_MAP_KEYS and isinstance(v, dict):
                out[k] = {mk: fn(mv) for mk, mv in v.items()}
            else:
                out[k] = _walk(v, fn)
        return out
    if isinstance(obj, list):
        return [_walk(x, fn) for x in obj]
    return obj


def to_cents(record: dict) -> dict:
    return _walk(record, cents)


def to_dollars(record: dict) -> dict:
    return _walk(record, dollars)
