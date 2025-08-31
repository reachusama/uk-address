# test_postcode.py
# Run with: pytest -q
import importlib
import pandas as pd
import pytest

import ukaddresskit.postcode as pc  # <-- change this import if your module has a different name


# ---------- Helpers ----------
def df(rows, cols):
    """Tiny helper to build a pandas DataFrame from list-of-tuples + column names."""
    return pd.DataFrame.from_records(rows, columns=cols)


# ---------- Basic parsing/normalisation ----------
def test_normalize_postcode():
    assert pc.normalize_postcode("sw1a1aa") == "SW1A 1AA"
    assert pc.normalize_postcode(" SW1A1AA ") == "SW1A 1AA"
    assert pc.normalize_postcode("SW1A 1AA") == "SW1A 1AA"


def test_normalize_postcode_heuristic_o_to_0():
    # 'O' used as the incode digit should be corrected to '0'
    assert pc.normalize_postcode("GL51OPU") == "GL51 0PU"


def test_normalize_postcode_invalid():
    with pytest.raises(ValueError):
        pc.normalize_postcode("NOT A CODE")


def test_extract_outcode_from_full_and_outcode():
    assert pc.extract_outcode("SW1A 1AA") == "SW1A"
    assert pc.extract_outcode("sw1a") == "SW1A"


def test_extract_outcode_invalid():
    with pytest.raises(ValueError):
        pc.extract_outcode("BADCODE")


# ---------- Monkeypatched loaders for postcode/outcode lookups ----------
@pytest.fixture(autouse=True)
def reset_module(monkeypatch):
    """
    Before each test, ensure any cached loaders don't leak state.
    We'll monkeypatch the loader functions directly with simple callables
    that return small DataFrames.
    """
    # Clear lru_cache on any existing loaders (if still present)
    for name in [
        "_load_postcode_town_df",
        "_load_outcode_county_df",
        "_load_postcode_locality_df",
        "_load_postcode_streets_df",
        "_load_postcode_property_mix_df",
    ]:
        func = getattr(pc, name, None)
        if func and hasattr(func, "cache_clear"):
            func.cache_clear()
    yield
    # After test, also try to clear caches again
    for name in [
        "_load_postcode_town_df",
        "_load_outcode_county_df",
        "_load_postcode_locality_df",
        "_load_postcode_streets_df",
        "_load_postcode_property_mix_df",
    ]:
        func = getattr(pc, name, None)
        if func and hasattr(func, "cache_clear"):
            func.cache_clear()


# ---------- get_town / get_county ----------
def test_get_town_found(monkeypatch):
    mock = df(
        rows=[("SW1A", "LONDON"), ("OX1", "OXFORD")],
        cols=["outcode", "post_town"],
    )
    monkeypatch.setattr(pc, "_load_postcode_town_df", lambda: mock)

    assert pc.get_town("SW1A 1AA") == "LONDON"
    assert pc.get_town("ox1 1aa") == "OXFORD"


def test_get_town_not_found(monkeypatch):
    mock = df(rows=[("OX1", "OXFORD")], cols=["outcode", "post_town"])
    monkeypatch.setattr(pc, "_load_postcode_town_df", lambda: mock)

    with pytest.raises(pc.PostcodeNotFound):
        pc.get_town("SW1A 1AA")


def test_get_county_some_missing(monkeypatch):
    mock = df(
        rows=[("SW1A", "GREATER LONDON")],
        cols=["outcode", "county"],
    )
    monkeypatch.setattr(pc, "_load_outcode_county_df", lambda: mock)

    assert pc.get_county("SW1A 1AA") == "GREATER LONDON"

    # Missing outcode returns None
    mock2 = df(rows=[], cols=["outcode", "county"])
    monkeypatch.setattr(pc, "_load_outcode_county_df", lambda: mock2)
    assert pc.get_county("SW1A 1AA") is None


# ---------- get_locality ----------
def test_get_locality_found(monkeypatch):
    # Loader returns columns: postcode, locality, pc_compact
    mock = df(
        rows=[
            ("SW1A 1AA", "WESTMINSTER", "SW1A1AA"),
            ("OX1 1AA", "OXFORD CENTRE", "OX11AA"),
        ],
        cols=["postcode", "locality", "pc_compact"],
    )
    monkeypatch.setattr(pc, "_load_postcode_locality_df", lambda: mock)

    assert pc.get_locality("sw1a 1aa") == "WESTMINSTER"


def test_get_locality_not_found(monkeypatch):
    mock = df(rows=[], cols=["postcode", "locality", "pc_compact"])
    monkeypatch.setattr(pc, "_load_postcode_locality_df", lambda: mock)

    with pytest.raises(pc.PostcodeNotFound):
        pc.get_locality("SW1A 1AA")


# ---------- get_streets ----------
def test_get_streets_sorted_unique(monkeypatch):
    mock = df(
        rows=[
            ("SW1A 1AA", "Downing Street", "SW1A1AA"),
            ("SW1A 1AA", "DOWNING STREET", "SW1A1AA"),
            ("SW1A 1AA", "Whitehall", "SW1A1AA"),
        ],
        cols=["postcode", "street", "pc_compact"],
    )
    monkeypatch.setattr(pc, "_load_postcode_streets_df", lambda: mock)
    assert pc.get_streets("SW1A 1AA") == ["DOWNING STREET", "WHITEHALL"]


def test_get_streets_not_found(monkeypatch):
    mock = df(rows=[], cols=["postcode", "street", "pc_compact"])
    monkeypatch.setattr(pc, "_load_postcode_streets_df", lambda: mock)

    with pytest.raises(pc.PostcodeNotFound):
        pc.get_streets("SW1A 1AA")


# ---------- get_property_mix ----------
def test_get_property_mix_numeric_and_strings(monkeypatch):
    # Provide a row where some values are numeric strings and some numeric
    mock = df(
        rows=[
            ("SW1A 1AA", "SW1A1AA", 5, "10", "0", 0, None),
            # columns: postcode, pc_compact, detached, semi_detached, terraced, flats, other
        ],
        cols=["postcode", "pc_compact", "detached", "semi_detached", "terraced", "flats", "other"],
    )
    monkeypatch.setattr(pc, "_load_postcode_property_mix_df", lambda: mock)

    mix = pc.get_property_mix("SW1A 1AA")
    assert mix == {
        "detached": 5.0,
        "semi_detached": 10.0,
        "terraced": 0.0,
        "flats": 0.0,
        # "other" omitted because None
    }


def test_get_property_mix_not_found(monkeypatch):
    mock = df(rows=[], cols=["postcode", "pc_compact", "detached"])
    monkeypatch.setattr(pc, "_load_postcode_property_mix_df", lambda: mock)

    with pytest.raises(pc.PostcodeNotFound):
        pc.get_property_mix("SW1A 1AA")
