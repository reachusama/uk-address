"""
Lightweight postcode utilities for UK addresses.

Features
--------
- normalize_postcode("sw1a1aa") -> "SW1A 1AA"
- extract_outcode("SW1A 1AA")   -> "SW1A"
- get_town(outcode|pc)          -> post town (from packaged CSV)
- get_county(outcode|pc)        -> county or None (best-effort; from packaged CSV)
- get_locality(pc)              -> locality name for a full postcode
- get_streets(pc)               -> list of street names for a postcode
- get_property_mix(pc)          -> dict of property-type mix at postcode (e.g., detached, flats, etc.)

Notes
-----
- Validation follows the standard UK postcode pattern (including GIR 0AA).
- Common user typo fixed: if the single incode digit is 'O', it's auto-corrected to '0'.
- All postcode-level lookups normalise to compact form (e.g. 'SW1A1AA') for matching.
- Underlying CSVs are packaged with the library and can be updated as new data is available.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Dict, List, Optional

import pandas as pd


class PostcodeNotFound(KeyError):
    """Raised when no lookup result exists for a valid postcode or outcode."""
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


def _normalize_postcode_compact(pc: str) -> str:
    """
    Normalize to strict postcode then remove the internal space: 'SW1A 1AA' -> 'SW1A1AA'.
    """
    return normalize_postcode(pc).replace(" ", "")


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


# === New packaged data loaders (postcode-level) ==============================

@lru_cache(maxsize=1)
def _load_postcode_locality_df() -> pd.DataFrame:
    """
    Load mapping: postcode_to_locality.csv
    Expected columns: 'postcode', 'locality'
    Postcodes should be compact (no space) or will be compacted at lookup time.
    """
    with resources.files("ukaddresskit.data.lookups").joinpath(
            "postcode_to_locality.csv"
    ).open("rb") as f:
        df = pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"postcode": "postcode", "locality": "locality"}
        )
    # Ensure a compact version for joins
    df["pc_compact"] = df["postcode"].str.replace(r"\s+", "", regex=True).str.upper()
    return df


@lru_cache(maxsize=1)
def _load_postcode_streets_df() -> pd.DataFrame:
    """
    Load mapping: postcode_to_streets.csv
    Expected columns: 'postcode', 'street'
    One row per (postcode, street) pair.
    """
    with resources.files("ukaddresskit.data.lookups").joinpath(
            "postcode_to_streets.csv"
    ).open("rb") as f:
        df = pd.read_csv(f, dtype=str, encoding="utf-8-sig").rename(
            columns={"postcode": "postcode", "street": "street"}
        )
    df["pc_compact"] = df["postcode"].str.replace(r"\s+", "", regex=True).str.upper()
    return df


@lru_cache(maxsize=1)
def _load_postcode_property_mix_df() -> pd.DataFrame:
    """
    Load mapping: postcode_property_mix.csv
    Expected columns: 'postcode', plus any set of property-type columns
    (e.g., 'detached', 'semi_detached', 'terraced', 'flats', etc.).
    Values may be counts or percentages; this function just returns what's provided.
    """
    with resources.files("ukaddresskit.data.lookups").joinpath(
            "postcode_property_mix.csv"
    ).open("rb") as f:
        df = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
    df = df.rename(columns={"postcode": "postcode"})
    df["pc_compact"] = df["postcode"].str.replace(r"\s+", "", regex=True).str.upper()
    # Try to coerce all non-id columns to numeric where possible; keep strings otherwise.
    for col in df.columns:
        if col not in ("postcode", "pc_compact"):
            df[col] = pd.to_numeric(df[col], errors="ignore")
    return df


# === Existing outcode-level lookups ==========================================

def get_town(pc_or_outcode: str) -> str:
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


# === New postcode-level utilities ============================================

def get_locality(postcode: str) -> str:
    """
    Return the locality (e.g., dependent locality / village / hamlet) for a full postcode.
    Raises:
        ValueError: if the postcode is invalid.
        PostcodeNotFound: if there is no locality for this postcode.
    """
    pc_compact = _normalize_postcode_compact(postcode)
    df = _load_postcode_locality_df()
    row = df.loc[df["pc_compact"] == pc_compact]
    if row.empty:
        raise PostcodeNotFound(f"No locality found for postcode {pc_compact}")
    # Prefer the first match if duplicates exist.
    val = row.iloc[0]["locality"]
    return None if pd.isna(val) or str(val).strip() == "" else str(val)


def get_streets(postcode: str) -> List[str]:
    """
    Return a list of street names present at a full postcode.
    The result is case-insensitive unique and uppercased for consistency.
    Raises:
        ValueError: if the postcode is invalid.
        PostcodeNotFound: if the postcode is not present in the mapping.
    """
    pc_compact = _normalize_postcode_compact(postcode)
    df = _load_postcode_streets_df()
    sub = df.loc[df["pc_compact"] == pc_compact]
    if sub.empty:
        raise PostcodeNotFound(f"No streets found for postcode {pc_compact}")

    streets = (
        sub["street"]
        .dropna()
        .map(lambda s: str(s).strip().upper())  # <- normalize to uppercase
        .loc[lambda s: s.ne("")]
        .drop_duplicates()  # case-insensitive uniqueness
        .sort_values()
        .tolist()
    )
    return streets


def get_property_mix(postcode: str) -> Dict[str, float]:
    """
    Return the property mix for a full postcode as a dict of {category: value}.
    Categories depend on the packaged CSV (e.g., 'detached', 'semi_detached', 'terraced', 'flats').
    Values are returned as-is from the data source (counts or percentages).

    Raises:
        ValueError: if the postcode is invalid.
        PostcodeNotFound: if the postcode is not present in the mapping.
    """
    pc_compact = _normalize_postcode_compact(postcode)
    df = _load_postcode_property_mix_df()
    row = df.loc[df["pc_compact"] == pc_compact]
    if row.empty:
        raise PostcodeNotFound(f"No property mix found for postcode {pc_compact}")

    row0 = row.iloc[0]
    out: Dict[str, float] = {}
    for col in df.columns:
        if col in ("postcode", "pc_compact"):
            continue
        val = row0[col]
        if pd.isna(val):
            continue
        # Try numeric first; if not numeric, keep as string but skip blanks.
        if isinstance(val, (int, float)):
            out[col] = float(val)
        else:
            sval = str(val).strip()
            if sval == "":
                continue
            try:
                out[col] = float(sval)
            except ValueError:
                # Non-numeric free text; you may choose to include it,
                # but here we only include numeric categories in the mix.
                continue
    if not out:
        # No usable categories present
        raise PostcodeNotFound(f"No numeric property categories for postcode {pc_compact}")
    return out
