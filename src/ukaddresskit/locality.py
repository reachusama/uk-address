"""
Locality → Town resolver (fast path, vectorised load).

CSV: ukaddresskit/data/lookups/locality_to_town.csv
Columns required: locality_key,town_city
Assumptions: values are already UPPERCASE and trimmed.

API
----
get_town_by_locality("Ab Kettleby")                 -> "MELTON MOWBRAY"
get_town_by_locality("Abberton", ambiguity="all")   -> ["COLCHESTER", "PERSHORE"]
list_towns_for_locality("Abberton")                 -> ["COLCHESTER", "PERSHORE"]
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Dict, List, Optional

import pandas as pd


# ---------------- Errors ----------------

class LocalityNotFound(KeyError):
    pass


class AmbiguousLocality(ValueError):
    def __init__(self, locality: str, towns: List[str]) -> None:
        super().__init__(f"Ambiguous locality {locality!r}: {towns}")
        self.locality = locality
        self.towns = towns


# -------------- Normalisation (lookup-time only) --------------

# Keep this light; CSV is already uppercase/trimmed.
# We normalise *input* to match the CSV shape.
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_MULTI_SPACE = re.compile(r"\s+")
_TOKEN_SYNONYMS = {
    "SAINT": "ST",
    "ST.": "ST",
    "&": "AND",
}


def _normalise_input_locality(s: str) -> str:
    """
    Canonicalise a user-supplied locality to match the CSV style:
    - uppercase
    - collapse punctuation/hyphens to spaces
    - collapse multiple spaces
    - simple token synonyms (Saint -> ST)
    """
    if not s:
        return ""
    s = s.strip().upper()
    s = _NON_ALNUM.sub(" ", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    if not s:
        return ""
    tokens = [_TOKEN_SYNONYMS.get(t, t) for t in s.split(" ")]
    return " ".join(tokens)


# -------------- Index model --------------

@dataclass(frozen=True)
class _LocalityIndex:
    unique: Dict[str, str]  # locality_norm -> single town
    counts: Dict[str, Dict[str, int]]  # locality_norm -> {town: count}


# -------------- Vectorised load (cached) --------------

@lru_cache(maxsize=1)
def _load_locality_index() -> _LocalityIndex:
    """
    Vectorised load of locality_to_town.csv with no per-row Python loops.
    We do a single groupby/value_counts to derive frequencies, then split
    into unique mappings and count dicts.
    """
    path = resources.files("ukaddresskit.data.lookups").joinpath("locality_to_town.csv")
    df = pd.read_csv(path.open("rb"), dtype=str, encoding="utf-8-sig")

    # Validate headers once
    cols = {c.lower(): c for c in df.columns}
    if "locality_key" not in cols or "town_city" not in cols:
        raise RuntimeError("locality_to_town.csv must have columns 'locality_key' and 'town_city'")

    loc_col = cols["locality_key"]
    town_col = cols["town_city"]

    # Keep only valid rows (vectorised)
    df = df[[loc_col, town_col]].dropna()
    # CSV is already uppercase/trimmed; just ensure single spaces (cheap, vectorised)
    # This keeps the key shape consistent if the file has punctuation like hyphens.
    df[loc_col] = (
        df[loc_col]
        .str.replace(r"[^A-Z0-9]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    df[town_col] = (
        df[town_col]
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # Frequency table: index is (locality, town), values are counts
    vc = df.groupby(loc_col, sort=False)[town_col].value_counts(sort=False)

    # nunique of towns per locality (vectorised)
    town_nu = df.groupby(loc_col, sort=False)[town_col].nunique()

    # Unique: where a locality maps to exactly one town
    unique_locs = town_nu.index[town_nu.eq(1)]
    # For those, grab the single town (vectorised: first() is fine because only one)
    unique_map = (
        df[df[loc_col].isin(unique_locs)]
        .drop_duplicates([loc_col, town_col])
        .set_index(loc_col)[town_col]
        .to_dict()
    )

    # Counts dict: for all localities, build {town: count}
    # We turn the value_counts Series into a DataFrame once, then pivot to dicts.
    vc_df = vc.rename("count").reset_index()  # columns: locality, town, count
    # Build nested dict locality -> {town: count}; this is one groupby-apply,
    # far fewer iterations than row-by-row loops.
    counts_dict: Dict[str, Dict[str, int]] = {
        loc: dict(zip(sub[town_col].to_list(), sub["count"].to_list()))
        for loc, sub in vc_df.groupby(loc_col, sort=False)
    }

    return _LocalityIndex(unique=unique_map, counts=counts_dict)


# -------------- Public API --------------

def list_towns_for_locality(locality: str) -> List[str]:
    """
    Return all towns for the given locality (normalised),
    ordered by frequency (desc) then alphabetical.
    """
    key = _normalise_input_locality(locality)
    if not key:
        raise LocalityNotFound("Empty locality")
    idx = _load_locality_index()
    counter = idx.counts.get(key)
    if not counter:
        raise LocalityNotFound(locality)

    # Sort by count desc, then name asc
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _cnt in items]


def get_town_by_locality(
        locality: str,
        *,
        ambiguity: str = "error",  # "error" | "most_common" | "first" | "all"
) -> Optional[str] | List[str]:
    """
    Resolve town for a locality using the cached index.

    ambiguity:
      - "error"       : raise AmbiguousLocality if multiple towns exist.
      - "most_common" : return the most frequent town (ties broken A→Z).
      - "first"       : return alphabetical first (deterministic).
      - "all"         : return list of candidates (ordered by frequency).
    """
    key = _normalise_input_locality(locality)
    if not key:
        raise LocalityNotFound("Empty locality")

    idx = _load_locality_index()

    # Fast path: unique mapping
    town = idx.unique.get(key)
    if town:
        return town

    # Ambiguous or missing
    counter = idx.counts.get(key)
    if not counter:
        raise LocalityNotFound(locality)

    towns_sorted = list_towns_for_locality(locality)

    if ambiguity == "error":
        raise AmbiguousLocality(locality, towns_sorted)
    if ambiguity == "all":
        return towns_sorted
    if ambiguity == "most_common":
        return towns_sorted[0]
    if ambiguity == "first":
        return sorted(counter.keys())[0]

    raise ValueError("ambiguity must be one of: 'error', 'most_common', 'first', 'all'")
