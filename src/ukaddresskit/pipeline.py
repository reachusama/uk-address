"""
High-level AddressParser: normalisation -> CRF tagging -> post-processing.

- Works with a pandas DataFrame that has an 'ADDRESS' column
- Uses ukaddresskit.parser.tag under the hood
- Optional progress bar if `tqdm` is installed
"""

from __future__ import annotations

import logging
import re
import sys
import warnings
from dataclasses import dataclass
from importlib import resources
from typing import Optional, Iterable

import pandas as pd

from .models import resolve_model_path
from .parser import tag as crf_tag

# quiet noisy warnings in notebooks
warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=UserWarning)
MODEL_PATH = str(resolve_model_path())

# Optional tqdm (no hard dependency)
try:
    from tqdm import tqdm as _tqdm  # type: ignore
except Exception:  # pragma: no cover
    def _tqdm(it: Iterable, **_: object) -> Iterable:
        return it

# Looser postcode regex (same shape as ukaddresskit.postcode, but local so we can search in text)
_POSTCODE_RE = re.compile(
    r"""([Gg][Ii][Rr]\s?0[Aa]{2}|(?:[A-PR-UWYZ][0-9][0-9]?|
        [A-PR-UWYZ][A-HK-Y][0-9][0-9]?|
        [A-PR-UWYZ][0-9][A-HJKPSTUW]?|
        [A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRVWXY]?)
        \s?[0-9][ABD-HJLN-UW-Z]{2})""",
    re.VERBOSE,
)


def _setup_logger(log: Optional[logging.Logger]) -> logging.Logger:
    if log is not None:
        return log
    logger = logging.getLogger("ukaddresskit.AddressParser")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def _read_lookup_csv(package_path: str, filename: str, **read_csv_kwargs) -> pd.DataFrame:
    """Read a CSV from ukaddresskit.data.lookups safely whether running from wheel/zip or source."""
    with resources.files(package_path).joinpath(filename).open("rb") as f:
        return pd.read_csv(f, **({"dtype": str, "encoding": "utf-8-sig"} | read_csv_kwargs))


@dataclass
class AddressParser:
    """
    High-level parser that wraps the CRF tagger with:
      - input normalisation
      - postcode extraction/normalisation tweaks
      - London borough fixups (optional lookup)
      - token post-processing into PAO/SAO parts

    Usage:
        ap = AddressParser()
        df_out = ap.parse(df_in)  # df_in must have 'ADDRESS'
    """

    model_path: Optional[str] = None
    expand_synonyms: bool = True
    log: Optional[logging.Logger] = None

    # ---- initialisation helpers ----
    def __post_init__(self) -> None:
        self.log = _setup_logger(self.log)
        self._model = MODEL_PATH

        # lookups packaged under ukaddresskit/data/lookups
        self._synonyms = _read_lookup_csv("ukaddresskit.data.lookups", "synonyms.csv") \
            if self.expand_synonyms else pd.DataFrame(columns=["from", "to"])
        self._counties = _read_lookup_csv("ukaddresskit.data.lookups", "counties.csv")

        # Optional London localities list. If file is missing, we just skip that fix step.
        try:
            self._london_localities = _read_lookup_csv("ukaddresskit.data.lookups", "london_localities.csv")
        except FileNotFoundError:
            self._london_localities = pd.DataFrame(columns=["locality"])

        # Precompile synonym patterns (word-boundary replace)
        self._syn_patterns = []
        if not self._synonyms.empty:
            for fro, to in self._synonyms[["from", "to"]].dropna().itertuples(index=False):
                pat = re.compile(rf"(?<!\w){re.escape(str(fro))}(?!\w)")
                self._syn_patterns.append((pat, str(to)))

        # Counties removal guard: don't strip if followed by a known road/flat etc.
        # We reuse your packaged lists indirectly via tokens.py,
        # but here we just do a conservative removal with an allowlist of suffixes.
        self._noncounty_suffixes = set(
            [
                "ROAD", "LANE", "STREET", "CLOSE", "DRIVE", "AVENUE", "SQUARE", "COURT", "PARK", "CRESCENT", "WAY",
                "WALK",
                "HEOL", "FFORDD", "HILL", "GARDENS", "GATE", "GROVE", "HOUSE", "VIEW", "BUILDING", "VILLAS", "LODGE",
                "PLACE", "ROW", "WHARF", "RISE", "TERRACE", "CROSS", "ENTERPRISE", "HATCH", "GREEN", "MEWS"
            ]
        )

    # ---- utilities ----
    @staticmethod
    def _extract_postcode(text: str) -> Optional[str]:
        """Find a postcode-like substring and ensure a space before the last 3 chars."""
        m = _POSTCODE_RE.search(text or "")
        if not m:
            return None
        pc = m.group(1).upper().replace(" ", "")
        return f"{pc[:-3]} {pc[-3:]}" if len(pc) > 3 else pc

    def _fix_london_boroughs(self, parsed: dict) -> dict:
        """If StreetName ends with a London locality and TownName mentions LONDON, move it to Locality."""
        if (
                not self._london_localities.empty
                and parsed.get("StreetName")
                and parsed.get("TownName")
                and "LONDON" in str(parsed["TownName"]).upper()
        ):
            street = str(parsed["StreetName"]).strip()
            for loc in self._london_localities["locality"].dropna().astype(str):
                loc_u = loc.upper()
                if street.endswith(loc_u):
                    parsed["Locality"] = loc_u
                    parsed["StreetName"] = street[: -len(loc_u)].strip()
                    break
        return parsed

    def _expand_synonyms_series(self, s: pd.Series) -> pd.Series:
        if not self._syn_patterns:
            return s
        out = s.fillna("")
        for pat, repl in self._syn_patterns:
            out = out.str.replace(pat, repl, regex=True)
        return out

    def _remove_county_keep_column(self, s: pd.Series) -> tuple[pd.Series, pd.Series]:
        """Remove county names but keep the first one seen in a 'County' column."""
        counties = self._counties["county"].dropna().astype(str).tolist()
        county_col = pd.Series([None] * len(s), index=s.index, dtype="object")

        # simple suffix guard to avoid stripping e.g. ESSEX ROAD
        suffix_rx = r"(?:\s+(?:" + "|".join(map(re.escape, sorted(self._noncounty_suffixes))) + r")\b)?"
        out = s.fillna("")

        for cty in counties:
            # match whole word, possibly followed by allowed suffix (we keep suffix, drop county)
            pat = re.compile(rf"(?i)(?<!\w){re.escape(cty)}(?!\w){suffix_rx}")
            has = out.str.contains(pat, regex=True, na=False)

            # set County if not set yet
            to_set = has & county_col.isna()
            if to_set.any():
                county_col.loc[to_set] = cty

            # remove the county token from the text (leave suffix if any)
            out = out.str.replace(pat, "", regex=True)

        # tidy spaces
        out = out.str.replace(r"\s{2,}", " ", regex=True).str.strip()
        return out, county_col

    # ---- main steps ----
    def _normalise(self, df: pd.DataFrame, out_col: str) -> pd.DataFrame:
        if "ADDRESS" not in df.columns:
            raise KeyError("Input DataFrame must contain an 'ADDRESS' column.")
        data = df.copy()

        # base cleanups
        s = data["ADDRESS"].astype(str).str.strip()
        s = s.str.replace(", ", " ", regex=False)
        s = s.str.replace(",", " ", regex=False)
        s = s.str.replace("\\", " ", regex=False)

        # normalise numeric ranges (avoid tokenizer confusion)
        s = s.str.replace(r"(\d+)\s*-\s*(\d+)", r"\1-\2", regex=True)
        s = s.str.replace(r"(\d+)\s*TO\s*(\d+)", r"\1-\2", regex=True)
        s = s.str.replace(r"(\d+)\s*/\s*(\d+)", r"\1-\2", regex=True)
        s = s.str.replace(r"(\d+[A-Za-z])\s*-\s*(\d+[A-Za-z])", r"\1-\2", regex=True)

        # synonyms
        if self.expand_synonyms:
            self.log.info("Expanding synonyms...")
            s = self._expand_synonyms_series(s)

        # remove counties but keep them in a column
        s, county_col = self._remove_county_keep_column(s)

        data[out_col] = s
        data["County"] = county_col
        return data

    def parse(self, df: pd.DataFrame, normalised_field_name: str = "ADDRESS_norm") -> pd.DataFrame:
        """Run full pipeline over a DataFrame; returns a new DataFrame with parsed columns."""
        self.log.info("Start parsing address data...")
        data = self._normalise(df, out_col=normalised_field_name)

        addrs = data[normalised_field_name].astype(str).tolist()
        self.log.info(f"{len(addrs)} addresses to parse...")

        # temp collectors
        cols = {
            "OrganisationName": [],
            "DepartmentName": [],
            "SubBuildingName": [],
            "BuildingName": [],
            "BuildingNumber": [],
            "StreetName": [],
            "Locality": [],
            "TownName": [],
            "Postcode": [],
        }

        for addr in _tqdm(addrs):
            parsed = crf_tag(addr.upper(), self._model) or {}

            # Regex extraction as a fallback / reconciler
            regex_pc = self._extract_postcode(addr)

            # reconcile postcode
            model_pc = parsed.get("Postcode")
            if model_pc and regex_pc and model_pc != regex_pc:
                parsed["Postcode"] = regex_pc
            elif not model_pc and regex_pc:
                parsed["Postcode"] = regex_pc

            # normalise postcode spacing/case
            if parsed.get("Postcode"):
                pc = str(parsed["Postcode"]).upper().replace(" ", "")
                if len(pc) > 4 and " " not in parsed["Postcode"]:
                    parsed["Postcode"] = f"{pc[:-3]} {pc[-3:]}"
                else:
                    parsed["Postcode"] = pc

            # London borough tweak
            parsed = self._fix_london_boroughs(parsed)

            # If number slipped into BuildingName, lift it into BuildingNumber
            if not parsed.get("BuildingNumber") and parsed.get("BuildingName"):
                parts = str(parsed["BuildingName"]).split(" ")
                if parts and parts[0].isdigit():
                    parsed["BuildingNumber"] = parts[0]

            # Clean trailing " CO"/" IN" in Locality (false tokens)
            if parsed.get("Locality"):
                loc = str(parsed["Locality"]).rstrip()
                if loc.endswith(" CO"):
                    parsed["Locality"] = loc[:-3]
                elif loc.endswith(" IN"):
                    parsed["Locality"] = loc[:-3]

            # "HOUSE" often belongs to SubBuilding
            if parsed.get("OrganisationName") == "HOUSE" and not parsed.get("SubBuildingName"):
                parsed["SubBuildingName"] = "HOUSE"

            # collect
            for k in cols:
                cols[k].append(parsed.get(k))

        # add to frame
        out = data.copy()
        for k, v in cols.items():
            out[k] = v
        out["PAOText"] = out["BuildingName"]
        out["SAOText"] = out["SubBuildingName"]

        # post-process into PAO/SAO number/suffix parts
        out = self._postprocess(out)
        return out

    # --- post-processing (ported & modernised) ---
    @staticmethod
    def _postprocess(df_in: pd.DataFrame) -> pd.DataFrame:
        df = df_in.copy()

        # postcode split (robust; no assumption about spaces)
        pc_raw = df["Postcode"].fillna("").astype(str).str.upper()
        pc_compact = pc_raw.str.replace(r"\s+", "", regex=True)

        # keep your historical column names:
        #   postcode_in  == part before the in-code (i.e., outcode)
        #   postcode_out == last 3 chars (in-code) if available
        df["postcode_in"] = pc_compact.where(pc_compact.str.len() > 3, None).str[:-3]
        df["postcode_out"] = pc_compact.where(pc_compact.str.len() >= 3, None).str[-3:]

        # init derived cols
        for c in (
                "PAOstartNumber", "PAOendNumber", "PAOstartSuffix", "PAOendSuffix",
                "SAOStartNumber", "SAOEndNumber", "SAOStartSuffix", "SAOEndSuffix",
        ):
            df[c] = None

        # Helper to safely .str.contains (NA-safe)
        def contains(s: pd.Series, pattern: str) -> pd.Series:
            return s.fillna("").str.contains(pattern, case=False, regex=True)

        # 1) building number → PAO start
        df["PAOstartNumber"] = df["BuildingNumber"]

        # 2) split 'n/n' in BuildingName into building + flat
        pat = r"(\d+)\/(\d+)"
        msk = contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk & df["PAOstartNumber"].isna(), "PAOstartNumber"] = ext[0]
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[1]

        # 3) SAO ranges in OrganisationName: 12A-12C  or 12-12C
        pat = r"(\d+)([A-Z])-(\d+)([A-Z])"
        msk = contains(df["OrganisationName"], pat)
        ext = df.loc[msk, "OrganisationName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOStartSuffix"].isna(), "SAOStartSuffix"] = ext[1]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[2]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[3]

        pat = r"(\d+)-(\d+)([A-Z])"
        msk = contains(df["OrganisationName"], pat)
        ext = df.loc[msk, "OrganisationName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[1]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[2]

        # 4) both SAO and PAO ranges inside BuildingName
        pat = r"(\d+)([A-Z])-(\d+)([A-Z]).*?(\d+)([A-Z])-(\d+)([A-Z])"
        msk = df["BuildingNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOStartSuffix"].isna(), "SAOStartSuffix"] = ext[1]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[2]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[3]
        df.loc[msk & df["PAOstartNumber"].isna(), "PAOstartNumber"] = ext[4]
        df.loc[msk & df["PAOstartSuffix"].isna(), "PAOstartSuffix"] = ext[5]
        df.loc[msk & df["PAOendNumber"].isna(), "PAOendNumber"] = ext[6]
        df.loc[msk & df["PAOendSuffix"].isna(), "PAOendSuffix"] = ext[7]

        pat = r"(\d+)([A-Z])-(\d+)([A-Z]).*?(\d+)-(\d+)"
        msk = df["BuildingNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOStartSuffix"].isna(), "SAOStartSuffix"] = ext[1]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[2]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[3]
        df.loc[msk & df["PAOstartNumber"].isna(), "PAOstartNumber"] = ext[4]
        df.loc[msk & df["PAOendNumber"].isna(), "PAOendNumber"] = ext[5]

        pat = r"(\d+)-(\d+)([A-Z]).*?(\d+)-(\d+)"
        msk = df["BuildingNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[1]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[2]
        df.loc[msk & df["PAOstartNumber"].isna(), "PAOstartNumber"] = ext[3]
        df.loc[msk & df["PAOendNumber"].isna(), "PAOendNumber"] = ext[4]

        pat = r"(\d+)([A-Z])-(\d+)([A-Z])\s.*?(\d+)([A-Z])"
        msk = df["BuildingNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[0]
        df.loc[msk & df["SAOStartSuffix"].isna(), "SAOStartSuffix"] = ext[1]
        df.loc[msk & df["SAOEndNumber"].isna(), "SAOEndNumber"] = ext[2]
        df.loc[msk & df["SAOEndSuffix"].isna(), "SAOEndSuffix"] = ext[3]
        df.loc[msk & df["PAOstartNumber"].isna(), "PAOstartNumber"] = ext[4]
        df.loc[msk & df["PAOstartSuffix"].isna(), "PAOstartSuffix"] = ext[5]

        # 5) extract PAO from BuildingName patterns
        pat = r"(\d+)([A-Z])-(\d+)([A-Z])"
        msk = df["PAOstartNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk, ["PAOstartNumber", "PAOstartSuffix", "PAOendNumber", "PAOendSuffix"]] = ext.values

        pat = r"(\d+)-(\d+)([A-Z])"
        msk = df["PAOstartNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk, ["PAOstartNumber", "PAOendNumber", "PAOendSuffix"]] = ext.values

        pat = r"(\d+)-(\d+)"
        msk = df["PAOstartNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk, ["PAOstartNumber", "PAOendNumber"]] = ext.values

        pat = r"(?<!-|\d)(\d+)([A-Z])(?!-)"
        msk = df["PAOstartNumber"].isna() & contains(df["BuildingName"], pat)
        ext = df.loc[msk, "BuildingName"].str.extract(pat)
        df.loc[msk, ["PAOstartNumber", "PAOstartSuffix"]] = ext.values

        # 6) SAO ranges in SubBuildingName
        pat = r"(\d+)([A-Z])-(\d+)([A-Z])"
        msk = contains(df["SubBuildingName"], pat)
        ext = df.loc[msk, "SubBuildingName"].str.extract(pat)
        df.loc[msk, ["SAOStartNumber", "SAOStartSuffix", "SAOEndNumber", "SAOEndSuffix"]] = ext.values

        pat = r"(\d+)-(\d+)([A-Z])"
        msk = contains(df["SubBuildingName"], pat)
        ext = df.loc[msk, "SubBuildingName"].str.extract(pat)
        df.loc[msk, ["SAOStartNumber", "SAOEndNumber", "SAOEndSuffix"]] = ext.values

        # 7) 'C2' -> suffix 'C', flat '2'
        pat = r"([A-Z])(\d+)"
        msk = contains(df["SubBuildingName"], pat)
        ext = df.loc[msk, "SubBuildingName"].str.extract(pat)
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = ext[1]
        df.loc[msk & df["SAOStartSuffix"].isna(), "SAOStartSuffix"] = ext[0]

        # 8) If SubBuildingName looks numeric-only, copy into SAOStartNumber
        msk = df["SubBuildingName"].fillna("").str.fullmatch(r"\d+")
        df.loc[msk & df["SAOStartNumber"].isna(), "SAOStartNumber"] = df.loc[msk, "SubBuildingName"]

        # 9) If StreetName contains a number and BuildingNumber is empty, copy it
        pat = r"(\d+)"
        msk = df["BuildingNumber"].isna() & contains(df["StreetName"], pat)
        ext = df.loc[msk, "StreetName"].str.extract(pat)
        df.loc[msk, "BuildingNumber"] = ext[0]
        df.loc[msk, "PAOstartNumber"] = ext[0]

        # 10) If SubBuildingName mentions FLAT/APARTMENT/UNIT, extract number part
        msk = df["SubBuildingName"].fillna("").str.contains(r"\b(flat|apartment|unit)\b", case=False, regex=True)
        df.loc[msk, "SAOStartNumber"] = (
            df.loc[msk, "SubBuildingName"]
            .str.upper()
            .str.replace("FLAT", "", regex=False)
            .str.replace("APARTMENT", "", regex=False)
            .str.replace("UNIT", "", regex=False)
            .str.strip()
        )

        # Numeric coercions (keep as strings where not applicable)
        for col in ("PAOstartNumber", "PAOendNumber", "SAOStartNumber", "SAOEndNumber"):
            df[col] = pd.to_numeric(df[col], errors="ignore")

        # Fill common string dummies to avoid None vs "" surprises
        for col in ("PAOText", "SAOText", "PAOstartSuffix", "PAOendSuffix", "SAOStartSuffix", "SAOEndSuffix"):
            df[col] = df[col].fillna("")

        for col in ("OrganisationName", "DepartmentName", "SubBuildingName"):
            df[col] = df[col].fillna("")

        return df
