# -*- coding: utf-8 -*-
"""Pure V1.4 prediction selection and classification helpers.

Prediction records are independent of scheduler ``states``. Their JSON-safe
shape is returned by ``new_prediction_data`` and validated at boundaries.
"""
import math
import random

SCHEMA = 1
STRATEGIES = ("conservative", "estimate", "optimistic")


def new_prediction_data():
    """Return an empty prediction document, separate from scheduler state."""
    return {"schema": SCHEMA, "selected": [], "rejected": [], "excluded": [],
            "effective": {"target": 0, "available": 0, "selected": 0}}


def validate_prediction_data(data):
    """Validate the persisted JSON shape; return the original object unchanged."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("prediction schema must be %d" % SCHEMA)
    for field in ("selected", "rejected", "excluded"):
        values = data.get(field)
        if not isinstance(values, list) or any(not isinstance(key, str) or not key
                                               for key in values):
            raise ValueError("prediction %s must be a list of non-empty keys" % field)
        if len(values) != len(set(values)):
            raise ValueError("prediction %s contains duplicate keys" % field)
    effective = data.get("effective")
    if not isinstance(effective, dict):
        raise ValueError("prediction effective counts must be an object")
    for field in ("target", "available", "selected"):
        value = effective.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("prediction effective.%s must be a non-negative integer" % field)
    if effective["selected"] != len(data["selected"]):
        raise ValueError("prediction selected count does not match selected keys")
    return data


def apply_strategy(estimate, error, strategy):
    """Resolve target count from an estimate and its absolute error margin."""
    if strategy not in STRATEGIES:
        raise ValueError("unknown prediction strategy: %r" % (strategy,))
    if (isinstance(estimate, bool) or isinstance(error, bool)
            or not isinstance(estimate, (int, float))
            or not isinstance(error, (int, float))
            or not math.isfinite(estimate) or not math.isfinite(error)
            or estimate < 0 or error < 0):
        raise ValueError("estimate and error must be finite non-negative numbers")
    value = {"conservative": estimate - error,
             "estimate": estimate,
             "optimistic": estimate + error}[strategy]
    return max(0, int(round(value)))


def _entry_bands(entries, bands):
    if bands is None:
        return {entry["w"]: entry.get("lvl", 0) for entry in entries}
    if isinstance(bands, dict):
        return bands
    if isinstance(bands, (list, tuple)) and len(bands) == len(entries):
        return {entry["w"]: level for entry, level in zip(entries, bands)}
    raise ValueError("bands must be a key-to-level mapping or align with entries")


def select_prediction_candidates(entries, states, target, bands=None,
                                 rejected=None, excluded=None, seed=None):
    """Choose easiest eligible keys, shuffling only a partially-used band.

    Any key with an explicit scheduler state, a pending entry marker, or listed
    in ``rejected``/``excluded`` is omitted. Exclusions do not cause replacement
    beyond the requested target. Returns ``(selected_keys, effective_counts)``.
    """
    if isinstance(target, bool) or not isinstance(target, int) or target < 0:
        raise ValueError("target must be a non-negative integer")
    if not isinstance(states, dict):
        raise ValueError("states must be an object")
    rejected, excluded = set(rejected or ()), set(excluded or ())
    levels = _entry_bands(entries, bands)
    eligible = []
    omitted = 0
    for entry in entries:
        key = entry.get("w")
        if not isinstance(key, str) or not key or key not in levels:
            continue
        if (key in states or key in rejected or key in excluded
                or entry.get("pending")):
            omitted += 1
            continue
        level = levels[key]
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level):
            raise ValueError("band levels must be finite numbers")
        eligible.append((level, key))

    # Stable level ordering; retain source order within fully selected bands.
    eligible.sort(key=lambda item: item[0])
    selected = set()
    rng = random.Random(seed)
    pos = 0
    while pos < len(eligible) and len(selected) < target:
        level = eligible[pos][0]
        end = pos + 1
        while end < len(eligible) and eligible[end][0] == level:
            end += 1
        band = eligible[pos:end]
        need = min(target - len(selected), len(band))
        if need < len(band):
            selected.update(key for _, key in rng.sample(band, need))
            break
        selected.update(key for _, key in band)
        pos = end

    counts = {"target": target, "available": len(eligible),
              "selected": len(selected), "excluded": omitted}
    return selected, counts
