"""
Lightweight postcode utilities:
- normalize_postcode("sw1a1aa") -> "SW1A 1AA"
- extract_outcode("SW1A 1AA") -> "SW1A"
- get_post_town(outcode) from packaged mapping
- get_county(outcode) from packaged mapping (best-effort; mapping file is small and editable)
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Optional

import pandas as pd


class PostcodeNotFound(KeyError):
    pass


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


def normalize_postcode(pc: str) -> str:
    """
    Uppercase and insert the single space before the incode, if valid.
    Raises ValueError if not a valid UK postcode pattern.
    """
    m = _POSTCODE_RE.match(pc or "")
    if not m:
        raise ValueError(f"Invalid UK postcode: {pc!r}")
    pc = m.group(1).upper().replace(" ", "")
    return f"{pc[:-3]} {pc[-3:]}"


def extract_outcode(pc: str) -> str:
    """
    Return the outward code (outcode), e.g. 'SW1A' from 'SW1A 1AA'.
    """
    npc = normalize_postcode(pc)
    return npc.split()[0]


@lru_cache(maxsize=1)
def _load_postcode_town_df() -> pd.DataFrame:
    with resources.files("ukaddresskit.data.lookups").joinpath(
        "postcode_district_to_town.csv"
    ).open("rb") as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"postcode": "outcode", "town": "post_town"}
        )


@lru_cache(maxsize=1)
def _load_outcode_county_df() -> pd.DataFrame:
    # Small editable mapping; ships with the package and can be extended.
    with resources.files("ukaddresskit.data.lookups").joinpath(
        "outcode_to_county.csv"
    ).open("rb") as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"outcode": "outcode", "county": "county"}
        )


def get_post_town(pc_or_outcode: str) -> str:
    """
    Lookup post town by outcode using packaged CSV.
    Raises PostcodeNotFound if unknown.
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
    Returns None if unknown. County names are not authoritative (depends on the mapping file).
    """
    outcode = extract_outcode(pc_or_outcode)
    df = _load_outcode_county_df()
    row = df.loc[df["outcode"].str.upper() == outcode]
    if row.empty:
        return None
    return row.iloc[0]["county"]
