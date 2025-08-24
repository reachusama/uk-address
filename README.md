# ukaddress-ner

UK address NER using CRFsuite with postcode utilities, a model manager, and a CLI.

## Install

```bash
pip install ukaddress-ner
```

## Quick Start

Python
```python
from ukaddress_ner import parse, tag, resolve_model_path

model = resolve_model_path()  # finds packaged baseline or your default
print(parse("10 Downing Street SW1A 2AA", model))
print(tag("Flat 2, 10 Queen Street, Bury BL8 1JG", model))
```

CLI
```cli
ukaddress-ner parse "10 Downing Street SW1A 2AA"         # auto-resolves model
ukaddress-ner tag   "Flat 2, 10 Queen Street, Bury BL8 1JG"
ukaddress-ner postcode "SW1A1AA" --town --county
```

## Postcode Helpers

```python
from ukaddress_ner import normalize_postcode, get_post_town, get_county
normalize_postcode("sw1a2aa")  # "SW1A 2AA"
get_post_town("SW1A 2AA")      # "LONDON"
get_county("SW1A 2AA")         # "Greater London" (if in mapping)
```


## Todo

- [ ] Add outcode_to_county.csv into lookups