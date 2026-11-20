"""
FlowForge — Redaction utilities.

SRS §8.2, §18.3:
Sensitive keys in step outputs, execution logs, and context dictionaries
must be redacted before persistence or logging.
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns matching sensitive key names (case-insensitive)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|auth(orization)?|cred(ential)?s?|bearer|private[_-]?key)",
    re.IGNORECASE,
)

REDACTED_PLACEHOLDER = "***"


def is_sensitive_key(key: str) -> bool:
    """Return True if *key* matches sensitive patterns."""
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def redact_data(data: Any) -> Any:  # noqa: ANN401
    """
    Recursively redact sensitive key-values in dicts, lists, and primitives.

    Returns a new deep copy of data with sensitive values replaced by '***'.
    """
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                result[k] = REDACTED_PLACEHOLDER
            else:
                result[k] = redact_data(v)
        return result
    elif isinstance(data, list):
        return [redact_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_data(item) for item in data)
    return data
