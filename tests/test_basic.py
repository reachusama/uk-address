import pytest

from ukaddresskit import tag
from ukaddresskit.tokens import tokenize


def test_tokenize_basic():
    s = "Flat 2, 10 Queen Street, Bury BL8 1JG"
    toks = tokenize(s)
    assert "FLAT" in [t.upper() for t in toks]
    assert any("BL8" in t for t in toks)


def test_tag_basic():
    s = "Flat 2, 10 Queen Street, Bury BL8 1JG"
    tags = tag(s)
    assert tags == {
        "SubBuildingName": "FLAT 2",
        "BuildingNumber": "10",
        "StreetName": "QUEEN STREET",
        "TownName": "BURY",
        "Postcode": "BL8 1JG",
    }
