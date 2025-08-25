# ukaddresskit

A tool kit to parse UK addresses using NER, and various utilities

## Install

```bash
pip install ukaddresskit
```

## Quick Start

**Tagger**

```python
from ukaddresskit.parser import tag

print(tag("10 Downing Street SW1A 2AA"))
```

**Output**

```json
{'BuildingNumber': '10', 'Locality': 'DOWNING', 'TownName': 'STREET', 'Postcode': 'SW1A 2AA'}
```

**Parser**

```
from ukaddresskit.parser import parse

print(parse("Flat 2, 10 Queen Street, Bury BL8 1JG"))
```

**Output**

```json
[('FLAT', 'SubBuildingName'), ('2', 'SubBuildingName'), ('10', 'BuildingNumber'), ('QUEEN', 'StreetName'), ('STREET', 'StreetName'), ('BURY', 'TownName'), ('BL8', 'Postcode'), ('1JG', 'Postcode')]
```

**AddressParser (Pre & Post processing)**

```python
import pandas as pd
from ukaddresskit.pipeline import AddressParser

ap = AddressParser()
df = pd.DataFrame({"ADDRESS": [
    "Flat 2, 10 Queen Street, Bury BL8 1JG",
]})
out = ap.parse(df)
fields = [
    "SubBuildingName", "BuildingName", "BuildingNumber",
    "StreetName", "Locality", "TownName", "Postcode", "County",
    "PAOstartNumber", "PAOendNumber", "PAOstartSuffix", "PAOendSuffix",
    "SAOStartNumber", "SAOEndNumber", "SAOStartSuffix", "SAOEndSuffix",
]

for i, row in out.iterrows():
    print(f"\nAddress #{i}")
    for col in fields:
        val = row.get(col)
        if pd.notna(val) and str(val) != "":
            print(f"  {col:16} {val}")
```

**Output**

```output
Address #0
  SubBuildingName  FLAT 2
  BuildingNumber   10
  StreetName       QUEEN STREET
  TownName         BURY
  Postcode         BL81JG
  PAOstartNumber   10.0
  SAOStartNumber   2
```

**Postcode Helpers**

```python
from ukaddresskit.postcode import normalize_postcode, get_post_town, get_county

normalize_postcode("sw1a2aa")  # "SW1A 2AA"
get_post_town("SW1A 2AA")      # "LONDON"
get_county("SW1A 2AA")         # "Greater London" (if in mapping)
```

## Todo

- [x] Add outcode_to_county.csv into lookups
- [x] Fix bugs in library not loading on Colab
- [ ] Create postcode fill utility
  - [x] get_town(postcode)
  - [x] get_county(postcode)
  - [ ] get_locality(postcode)
  - [ ] get_streets(postcode) → array of street names
  - [ ] get_address_counts(postcode)
  - [ ] property mix at postcode
- [ ] Create address populate utility (add missing address components - town, county, etc)
- [ ] Create address linkage utility
- [ ] Create address formatting utility
- [ ] Define test cases, organise code
- [ ] Create [online docs](https://medium.com/practical-coding/documenting-your-python-library-from-zero-to-website-488f87ae58f5)