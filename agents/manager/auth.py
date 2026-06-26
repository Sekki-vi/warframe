"""Stub user auth levels for Streamlit sidebar."""
from __future__ import annotations

_LABELS = {
    0: "Guest",
    1: "Operator",
    2: "Trusted",
    3: "Moderator",
    4: "Admin",
}


def get_user_info(user_id: str) -> dict:
    level = 1 if user_id and user_id != "guest" else 0
    return {"auth_level": level, "label": _LABELS.get(level, "Operator")}
