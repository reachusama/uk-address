"""
Tokens & feature extraction for UK address NER (CRF).
Refactored to:
- Avoid I/O on import (lazy load lookup CSVs)
- Use importlib.resources to access package data
- Keep your original features with a few tidy-ups
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from importlib import resources
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

import pandas as pd
from lxml import etree

# Labels expected from training
LABELS: List[str] = [
    "OrganisationName",
    "DepartmentName",
    "SubBuildingName",
    "BuildingName",
    "BuildingNumber",
    "StreetName",
    "Locality",
    "TownName",
    "Postcode",
]

DIRECTIONS = {
    "N",
    "S",
    "E",
    "W",
    "NE",
    "NW",
    "SE",
    "SW",
    "NORTH",
    "SOUTH",
    "EAST",
    "WEST",
    "NORTHEAST",
    "NORTHWEST",
    "SOUTHEAST",
    "SOUTHWEST",
}

FLAT = {
    "FLAT",
    "FLT",
    "APARTMENT",
    "APPTS",
    "APPT",
    "APTS",
    "APT",
    "ROOM",
    "ANNEX",
    "ANNEXE",
    "UNIT",
    "BLOCK",
    "BLK",
}
COMPANY = {
    "CIC",
    "CIO",
    "LLP",
    "LP",
    "LTD",
    "LIMITED",
    "CYF",
    "PLC",
    "CCC",
    "UNLTD",
    "ULTD",
}
ROAD = {
    "ROAD",
    "RAOD",
    "RD",
    "DRIVE",
    "DR",
    "STREET",
    "STRT",
    "AVENUE",
    "AVENEU",
    "SQUARE",
    "LANE",
    "LNE",
    "LN",
    "COURT",
    "CRT",
    "CT",
    "PARK",
    "PK",
    "GRDN",
    "GARDEN",
    "CRESCENT",
    "CLOSE",
    "CL",
    "WALK",
    "WAY",
    "TERRACE",
    "BVLD",
    "HEOL",
    "FFORDD",
    "PLACE",
    "GARDENS",
    "GROVE",
    "VIEW",
    "HILL",
    "GREEN",
}
Residential = {
    "HOUSE",
    "HSE",
    "FARM",
    "LODGE",
    "COTTAGE",
    "COTTAGES",
    "VILLA",
    "VILLAS",
    "MAISONETTE",
    "MEWS",
}
Business = {
    "OFFICE",
    "HOSPITAL",
    "CARE",
    "CLUB",
    "BANK",
    "BAR",
    "UK",
    "SOCIETY",
    "PRISON",
    "HMP",
    "RC",
    "UWE",
    "UEA",
    "LSE",
    "KCL",
    "UCL",
    "UNI",
    "UNIV",
    "UNIVERSITY",
    "UNIVERISTY",
}
Locational = {
    "BASEMENT",
    "GROUND",
    "UPPER",
    "ABOVE",
    "TOP",
    "LOWER",
    "FLOOR",
    "HIGHER",
    "ATTIC",
    "LEFT",
    "RIGHT",
    "FRONT",
    "BACK",
    "REAR",
    "WHOLE",
    "PART",
    "SIDE",
}
Ordinal = {
    "0TH",
    "ZEROTH",
    "0ED",
    "SERO",
    "SEROFED",
    "DIM",
    "DIMFED",
    "1ST",
    "FIRST",
    "1AF",
    "CYNTA",
    "CYNTAF",
    "GYNTAF",
    "2ND",
    "SECOND",
    "2AIL",
    "AIL",
    "AILFED",
    "3RD",
    "THIRD",
    "3YDD",
    "TRYDYDD",
    "TRYDEDD",
    "4TH",
    "FOURTH",
    "4YDD",
    "PEDWERYDD",
    "PEDWAREDD",
    "5TH",
    "FIFTH",
    "5ED",
    "PUMED",
    "6TH",
    "SIXTH",
    "6ED",
    "CHWECHED",
    "7TH",
    "SEVENTH",
    "7FED",
    "SEITHFED",
    "8TH",
    "EIGHTH",
    "8FED",
    "WYTHFED",
    "9TH",
    "NINTH",
    "9FED",
    "NAWFED",
    "10TH",
    "TENTH",
    "10FED",
    "DEGFED",
    "11TH",
    "ELEVENTH",
    "11FED",
    "UNFED",
    "DDEG",
    "12TH",
    "TWELFTH",
    "12FED",
    "DEUDDEGFED",
}
non_county = {
    "OFFICE",
    "HOSPITAL",
    "CARE",
    "CLUB",
    "BANK",
    "BAR",
    "SOCIETY",
    "PRISON",
    "HMP",
    "UNI",
    "UNIV",
    "UNIVERSITY",
    "UNIVERISTY",
}
noncounty = non_county | COMPANY | FLAT | Residential | ROAD
nonCountyIdentification = list(sorted(noncounty))


# ---------- Data loading (lazy, via package resources) ----------


@lru_cache(maxsize=1)
def _load_counties() -> List[str]:
    with resources.files("ukaddresskit.data.lookups").joinpath("counties.csv").open(
        "rb"
    ) as f:
        df = pd.read_csv(f, usecols=["county"], dtype=str, encoding="utf-8-sig")
    return df["county"].dropna().astype(str).str.strip().tolist()


@lru_cache(maxsize=1)
def _load_synonyms() -> Dict[str, str]:
    with resources.files("ukaddresskit.data.lookups").joinpath("synonyms.csv").open(
        "rb"
    ) as f:
        df = pd.read_csv(
            f, usecols=["from", "to"], dtype=str, encoding="utf-8-sig"
        ).dropna()
    return dict(zip(df["from"].str.strip(), df["to"].str.strip()))


@lru_cache(maxsize=1)
def _load_outcode_posttown() -> Tuple[set, set]:
    with resources.files("ukaddresskit.data.lookups").joinpath(
        "postcode_district_to_town.csv"
    ).open("rb") as f:
        df = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
    outcodes = set(df["postcode"].astype(str).str.strip().str.upper().tolist())
    towns = set(df["town"].astype(str).str.strip().str.upper().tolist())
    return outcodes, towns


def synonym(token: str) -> str:
    lut = _load_synonyms()
    return lut.get(token, token)


def _stripFormatting(collection):
    collection.text = None
    for element in collection:
        element.text = None
        element.tail = None
    return collection


def readXML(xmlFile: str) -> Iterator[Tuple[str, List[Tuple[str, str]]]]:
    component_string_list: List[bytes] = []

    if not os.path.isfile(xmlFile):
        raise FileNotFoundError(f"{xmlFile} does not exist")

    with open(xmlFile, "rb") as f:
        tree = etree.parse(f)
        file_xml = _stripFormatting(tree.getroot())
        for component_etree in file_xml:
            component_string_list.append(etree.tostring(component_etree))

    for component_string in component_string_list:
        sequence_xml = etree.fromstring(component_string)
        raw_text = etree.tostring(sequence_xml, method="text", encoding="utf-8").decode(
            "utf-8"
        )
        sequence_components: List[Tuple[str, str]] = []
        for component in list(sequence_xml):
            sequence_components.append((component.text or "", component.tag))
        yield raw_text, sequence_components


def digits(token: str) -> str:
    if token.isdigit():
        return "all_digits"
    elif any(ch.isdigit() for ch in token):
        return "some_digits"
    return "no_digits"


def tokenFeatures(token: str) -> Dict:
    token_clean = token.upper()
    OUTCODES, POSTTOWNS = _load_outcode_posttown()

    features = {
        "digits": digits(token_clean),
        "word": (token_clean if not token_clean.isdigit() else False),
        "length": (
            "d:" + str(len(token_clean))
            if token_clean.isdigit()
            else "w:" + str(len(token_clean))
        ),
        "endsinpunc": (token[-1] if re.match(r".+\.$", token) else False),
        "directional": token_clean in DIRECTIONS,
        "outcode": token_clean in OUTCODES,
        "posttown": token_clean in POSTTOWNS,
        "has.vowels": bool(set(token_clean) & set("AEIOU")),
        "flat": token_clean in FLAT,
        "company": token_clean in COMPANY,
        "road": token_clean in ROAD,
        "residential": token_clean in Residential,
        "business": token_clean in Business,
        "locational": token_clean in Locational,
        "ordinal": token_clean in Ordinal,
        "hyphenations": token_clean.count("-"),
    }
    return features


def tokens2features(tokens: Sequence[str]) -> List[Dict]:
    if not tokens:
        return []

    feature_sequence: List[Dict] = [tokenFeatures(tokens[0])]
    previous_features = feature_sequence[-1].copy()

    for token in tokens[1:]:
        token_features = tokenFeatures(token)
        current_features = token_features.copy()
        feature_sequence[-1]["next"] = current_features
        token_features["previous"] = previous_features
        feature_sequence.append(token_features)
        previous_features = current_features

    if len(feature_sequence) > 1:
        feature_sequence[0]["rawstring.start"] = True
        feature_sequence[-1]["rawstring.end"] = True
        feature_sequence[1]["previous"]["rawstring.start"] = True
        feature_sequence[-2]["next"]["rawstring.end"] = True
    else:
        feature_sequence[0]["singleton"] = True

    return feature_sequence


def replaceSynonyms(tokens: Iterable[str]) -> List[str]:
    lut = _load_synonyms()
    return [lut.get(x, x) for x in tokens]


def removeCounties(in_string: str) -> str:
    counties = _load_counties()

    # If preceded by ON|DINAS|UPON or a digit, keep county (e.g., "Stratford upon Avon")
    c_except = [r"ON\s", r"DINAS\s", r"UPON\s", r"[0-9]\s"]
    look_behind = r"(?<!\b{0})({1})".format(
        r")(?<!\b".join(c_except), "|".join(map(re.escape, counties))
    )

    # If followed by "road-like" things, keep it (do not strip)
    a = r"\b|\s".join(map(re.escape, nonCountyIdentification))
    look_ahead = rf"(?!(\s{a}\b))"

    final_regex = look_behind + look_ahead
    return re.compile(final_regex).sub("", in_string)


def tokenize(raw_string):
    if isinstance(raw_string, bytes):
        try:
            raw_string = raw_string.decode("utf-8")
        except Exception:
            raw_string = str(raw_string)

    upperInput = raw_string.upper()
    inputWithoutCounties = removeCounties(upperInput)

    # Normalise ranges like "12 - 14" -> "12-14"
    tokens = re.sub(r"(\d+[A-Z]?) *- *(\d+[A-Z]?)", r"\1-\2", inputWithoutCounties)
    tokens = re.sub(r"(\d+)/(\d+)", r"\1-\2", tokens)
    tokens = re.sub(r"(\d+) *TO *(\d+)", r"\1-\2", tokens)

    tokens = (
        tokens.replace(" IN ", " ")
        .replace(" CO ", " ")
        .replace(" - ", " ")
        .replace(",", " ")
        .replace("\\", " ")
    )

    tokens_list = tokens.split()
    preprocessed_string = removeCounties(" ".join(replaceSynonyms(tokens_list)))

    re_tokens = re.compile(r"\(*\b[^\s,;#&()]+[.,;)\n]*|[#&]", re.VERBOSE | re.UNICODE)
    out = re_tokens.findall(preprocessed_string)
    return out if out else []


def readData(xmlFile: str):
    data = readXML(xmlFile)
    X: List[List[Dict]] = []
    y: List[List[str]] = []
    for _, components in data:
        tokens, labels = list(zip(*components)) if components else ([], [])
        X.append(tokens2features(list(tokens)))
        y.append(list(labels))
    return X, y
