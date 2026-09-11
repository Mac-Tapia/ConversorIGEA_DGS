"""Universal naming helpers for CYMDIST/IGEA NetworkIDs and selectors.

Feeder IDs vary by utility (e.g. ``NET_2030_142_IN111``, ``ALIMENTADOR-12``,
``Feeder.A1``). Short names and selectors must not assume one company's pattern.
"""

from __future__ import annotations

import re

# Tokens may be separated by underscore, hyphen, dot, slash or backslash.
_TOKEN_SPLIT = re.compile(r'[_\-./\\]+')


def feeder_tokens(network_id: str) -> list[str]:
    text = (network_id or '').strip()
    if not text:
        return []
    return [part for part in _TOKEN_SPLIT.split(text) if part]


def feeder_short_name(network_id: str) -> str:
    """Display / output basename for a NetworkID (last path-like token)."""
    parts = feeder_tokens(network_id)
    return parts[-1] if parts else (network_id or '').strip()


def sort_key_feeder(network_id: str) -> str:
    return feeder_short_name(network_id).lower()
