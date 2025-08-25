"""
Lightweight postcode utilities for UK addresses.

Features
--------
- normalize_postcode("sw1a1aa") -> "SW1A 1AA"
- extract_outcode("SW1A 1AA")   -> "SW1A"
- get_post_town(outcode|pc)     -> post town (from packaged CSV)
- get_county(outcode|pc)        -> county or None (best-effort; from packaged CSV)

Notes
-----
- Validation follows the standard UK postcode pattern (including GIR 0AA).
- Common user typo fixed: if the single incode digit is 'O', it's auto-corrected to '0'.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Optional

import pandas as pd


class PostcodeNotFound(KeyError):
    """Raised when no lookup result exists for a valid outcode."""
    pass


# Strict *full postcode* regex (case-insensitive), allowing optional internal space.
# Final two letters exclude CIKMOV; see Royal Mail format guidance.
_POSTCODE_RE = re.compile(
    r"""
    ^\s*
    (GIR\s?0AA|
     (?:[A-PR-UWYZ][0-9][0-9]?|
        [A-PR-UWYZ][A-HK-Y][0-9][0-9]?|
        [A-PR-UWYZ][0-9][A-HJKPSTUW]?|
        [A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRVWXY]?)
     \s?[0-9][ABD-HJLN-UW-Z]{2})
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

# *Outcode* regex (no incode). Accepts the outward formats above.
_OUTCODE_RE = re.compile(
    r"""
    ^\s*
    (?:GIR|  # rare, but allow for symmetry (won't be used in practice)
     [A-PR-UWYZ][0-9][0-9]?|
     [A-PR-UWYZ][A-HK-Y][0-9][0-9]?|
     [A-PR-UWYZ][0-9][A-HJKPSTUW]?|
     [A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRVWXY]?)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _fix_common_incode_o_typo(s: str) -> str:
    """
    Fix the very common 'O' (letter) in place of the single incode digit.
    Example: 'GL51OPU' -> 'GL510PU'
    Only applies if length is at least 5 and the 3-char incode exists.
    """
    raw = re.sub(r"\s+", "", s.upper())
    if len(raw) >= 5:
        # The incode is the last 3 chars: D LL (digit + two letters)
        incode = raw[-3:]
        if len(incode) == 3 and not incode[0].isdigit() and incode[0] == "O":
            return raw[:-3] + "0" + incode[1:]
    return raw


def normalize_postcode(pc: str) -> str:
    """
    Uppercase and insert the single space before the incode, if valid.
    A small heuristic corrects 'O'->'0' when it's used as the incode digit.

    Raises:
        ValueError: if not a valid UK postcode pattern after heuristic.
    """
    s = pc or ""
    # First attempt: strict match as-is
    m = _POSTCODE_RE.match(s)
    if not m:
        # Heuristic pass to fix 'O' as incode digit
        s2 = _fix_common_incode_o_typo(s)
        m = _POSTCODE_RE.match(s2)
        if not m:
            raise ValueError(f"Invalid UK postcode: {pc!r}")
        pc_compact = m.group(1).upper().replace(" ", "")
    else:
        pc_compact = m.group(1).upper().replace(" ", "")

    return f"{pc_compact[:-3]} {pc_compact[-3:]}"


def extract_outcode(pc_or_outcode: str) -> str:
    """
    Return the outward code (outcode).
    Accepts either a full postcode or an outcode string.

    Raises:
        ValueError: if neither a valid postcode nor a valid outcode.
    """
    s = pc_or_outcode or ""

    # Try full postcode first (with the same heuristic)
    try:
        npc = normalize_postcode(s)
        return npc.split()[0]
    except ValueError:
        pass

    # Then try a plain outcode
    if _OUTCODE_RE.match(s or ""):
        return re.sub(r"\s+", "", s).upper()

    raise ValueError(f"Invalid UK postcode or outcode: {pc_or_outcode!r}")


@lru_cache(maxsize=1)
def _load_postcode_town_df() -> pd.DataFrame:
    """
    Load packaged mapping: postcode_district_to_town.csv
    Expected columns in CSV: 'postcode' (outcode), 'town' (post town)
    """
    with resources.files("ukaddresskit.data.lookups").joinpath(
            "postcode_district_to_town.csv"
    ).open("rb") as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"postcode": "outcode", "town": "post_town"}
        )


@lru_cache(maxsize=1)
def _load_outcode_county_df() -> pd.DataFrame:
    """
    Load small editable mapping: outcode_to_county.csv
    Expected columns in CSV: 'outcode', 'county'
    """
    with resources.files("ukaddresskit.data.lookups").joinpath(
            "outcode_to_county.csv"
    ).open("rb") as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"outcode": "outcode", "county": "county"}
        )


def get_post_town(pc_or_outcode: str) -> str:
    """
    Lookup post town by outcode using packaged CSV.
    Accepts either a full postcode or an outcode.
    Raises PostcodeNotFound if the outcode isn't present in the mapping.
    """
    outcode = extract_outcode(pc_or_outcode)
    df = _load_postcode_town_df()
    row = df.loc[df["outcode"].str.upper() == outcode]
    if row.empty:
        raise PostcodeNotFound(f"No post town found for outcode {outcode}")
    return row.iloc[0]["post_town"]


def get_county(pc_or_outcode: str) -> Optional[str]:
    """
    Best-effort county from outcode using packaged mapping.
    Accepts either a full postcode or an outcode.
    Returns None if unknown. County names are not authoritative.
    """
    outcode = extract_outcode(pc_or_outcode)
    df = _load_outcode_county_df()
    row = df.loc[df["outcode"].str.upper() == outcode]
    if row.empty:
        return None
    return row.iloc[0]["county"]
