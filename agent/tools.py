"""Tools the Strands agent can call. The docstrings are what the model reads."""
from strands import tool

import store

KINDS = {"medicine", "appointment", "other"}


def _fmt(item: dict) -> str:
    t = store.parse_time(item["due_at"])
    note = f" ({item['note']})" if item.get("note") else ""
    return f"[{item['reminder_id']}] {t:%m/%d %H:%M} {item['title']}{note} - {item['kind']}, {item['status']}"


@tool
def add_reminders(title: str, kind: str, due_times: list[str], note: str = "") -> str:
    """Register reminders for the user. Call once per item; pass every time in due_times.

    For medicine, register each dose time separately, e.g. "1日3回 毎食後" ->
    three times (breakfast 08:00, lunch 12:30, dinner 18:30 unless the user says otherwise).

    Args:
        title: Short label in Japanese, e.g. "血圧のお薬 1錠" or "かまた内科 受診".
        kind: One of "medicine", "appointment", "other".
        due_times: List of Japan-time datetimes "YYYY-MM-DDTHH:MM", e.g. ["2026-11-03T08:00"].
        note: Optional extra info, e.g. "食後" or "保険証を持っていく".
    """
    if kind not in KINDS:
        kind = "other"
    if not due_times:
        return "No times given. Ask the user when."
    if len(due_times) > 14:
        return "Too many times (max 14). Register fewer, e.g. today and tomorrow only."
    created, errors = [], []
    for value in due_times:
        try:
            created.append(store.add_reminder(title, kind, store.parse_time(value), note))
        except ValueError:
            errors.append(value)
    lines = [_fmt(i) for i in created]
    if errors:
        lines.append(f"Could not read these times: {errors}")
    alert = " Family will be alerted if a dose is not confirmed." if kind == "medicine" else ""
    return f"Registered {len(created)} reminder(s).{alert}\n" + "\n".join(lines)


@tool
def list_reminders(include_done: bool = False) -> str:
    """List the user's reminders (pending only by default), sorted by time.

    Args:
        include_done: Also show completed and cancelled reminders.
    """
    items = store.list_reminders(include_done)
    return "\n".join(_fmt(i) for i in items) if items else "No reminders."


@tool
def confirm_done(reminder_id: str) -> str:
    """Mark a reminder as done, e.g. when the user says they took their medicine.
    This also stops the family alert for that dose. Use list_reminders first to find the id.

    Args:
        reminder_id: The 8-character id shown in brackets by list_reminders.
    """
    item = store.complete(reminder_id)
    return f"Done: {_fmt(item)}" if item else f"No reminder with id {reminder_id}."


@tool
def cancel_reminder(reminder_id: str) -> str:
    """Cancel a reminder the user no longer needs.

    Args:
        reminder_id: The 8-character id shown in brackets by list_reminders.
    """
    item = store.cancel(reminder_id)
    return f"Cancelled: {_fmt(item)}" if item else f"No reminder with id {reminder_id}."


@tool
def notify_family(message: str) -> str:
    """Send a short message to the user's family by email.
    Use when the user asks you to contact family, or says they feel unwell.

    Args:
        message: Plain Japanese message for the family, e.g. "体調がすぐれないそうです。連絡してあげてください。"
    """
    return store.notify_family(message)


ALL_TOOLS = [add_reminders, list_reminders, confirm_done, cancel_reminder, notify_family]
