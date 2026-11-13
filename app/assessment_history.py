# -*- coding: utf-8 -*-
"""V1.4.2 history boundaries: preserve old evidence, never rescore it.

This module has no filesystem or Qt side effects.  Archival is performed inside
Card's existing answer/session/history atomic-save transaction.
"""
import copy
import math

ALGORITHM = "vst-cat-v142"
UNIT = "frequency_ranked_entries"
MEASUREMENT_SCHEMA = 3


def is_current(record):
    return (isinstance(record, dict) and record.get("algo") == ALGORITHM
            and record.get("measurement_schema") == MEASUREMENT_SCHEMA
            and record.get("unit") == UNIT)


def series_key(record):
    """A different bank, unit or measurement model is a different scale."""
    return (record.get("algo", "legacy"), record.get("bank_id", "legacy"),
            record.get("unit", "legacy"), record.get("measurement_schema", 0))


def plottable(record):
    if not isinstance(record, dict) or record.get("estimate_available") is False:
        return False
    for key in ("ts", "vocab"):
        value = record.get(key)
        try:
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                return False
        except OverflowError:
            return False
    # A partially answered new attempt is not a completed measurement trend.
    return not is_current(record) or (record.get("completed") is True
                                     and record.get("estimate_available") is True)


def comparable(history, reference):
    key = series_key(reference)
    return [row for row in history if series_key(row) == key and plottable(row)]


def current_trend(history, bank_id):
    return [row for row in history if is_current(row)
            and row.get("bank_id") == bank_id and plottable(row)]


def archive_session(progress, timestamp, reason):
    """Preserve the exact old snapshot, not a newly computed legacy score.

    No existing history entry or session object is edited.  The caller replaces
    quiz_session only after this succeeds and rolls back on save failures.
    """
    session = progress.get("quiz_session")
    if session is None:
        return
    archives = progress.get("quiz_archives", [])
    if not isinstance(archives, list):
        raise ValueError("quiz_archives must be a list; existing data was retained")
    if any(isinstance(row, dict) and row.get("session") == session for row in archives):
        return
    if "quiz_archives" not in progress:
        progress["quiz_archives"] = archives
    archives.append({"archived_at": timestamp, "reason": reason,
                     "session": copy.deepcopy(session)})
