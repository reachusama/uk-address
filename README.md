# ukaddress-ner

UK address NER using CRFsuite with postcode utilities, a model manager, and a CLI.

## Install

```bash
pip install uk-address
```

## Quick Start

Python
```python
from ukaddress import parse, tag


print(parse("10 Downing Street SW1A 2AA"))
print(tag("Flat 2, 10 Queen Street, Bury BL8 1JG"))
```

CLI
```cli
ukaddress parse "10 Downing Street SW1A 2AA"         # auto-resolves model
ukaddress tag   "Flat 2, 10 Queen Street, Bury BL8 1JG"
ukaddress postcode "SW1A1AA" --town --county
```

## Postcode Helpers

```python
from ukaddress import normalize_postcode, get_post_town, get_county
normalize_postcode("sw1a2aa")  # "SW1A 2AA"
get_post_town("SW1A 2AA")      # "LONDON"
get_county("SW1A 2AA")         # "Greater London" (if in mapping)
```


## Todo

- [ ] Add outcode_to_county.csv into lookups