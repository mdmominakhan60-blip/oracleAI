"""Safe formatting helpers for Telegram HTML parse mode."""
from __future__ import annotations

import re
from html import escape

_ALLOWED_SIMPLE_TAGS = re.compile(r"&lt;(\/?)((?:b)|(?:i))&gt;", re.IGNORECASE)


def tg_esc(value: object) -> str:
    """Escape untrusted text for Telegram HTML without enabling markup."""
    return escape(str(value if value is not None else ""), quote=False)


def tg_rich(value: object) -> str:
    """Allow only balanced, attribute-free b/i tags after escaping everything else."""
    escaped = tg_esc(value)
    if not all(escaped.count(f"&lt;{tag}&gt;") == escaped.count(f"&lt;/{tag}&gt;")
               for tag in ("b", "i", "B", "I")):
        return escaped
    return _ALLOWED_SIMPLE_TAGS.sub(
        lambda match: f"<{match.group(1)}{match.group(2).lower()}>", escaped,
    )
