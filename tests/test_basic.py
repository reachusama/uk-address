import pytest

from ukaddresskit import tag
from ukaddresskit.postcode import (
    PostcodeNotFound,
    extract_outcode,
    get_county,
    get_post_town,
    normalize_postcode,
)
from ukaddresskit.tokens import tokenize

# def test_postcode_normalize():
#     assert normalize_postcode("sw1a1aa") == "SW1A 1AA"
#     assert extract_outcode("SW1A1AA") == "SW1A"


# def test_post_town_lookup():
#     assert get_post_town("SW1A 1AA") == "LONDON"
#     with pytest.raises(PostcodeNotFound):
#         get_post_town("ZZ1 1ZZ")


# def test_county_lookup():
#     assert get_county("SW1A 1AA") == "Greater London"
#     assert get_county("ZZ1 1ZZ") is None


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
