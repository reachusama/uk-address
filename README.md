# ukaddresskit

[![CI](https://github.com/reachusama/ukaddresskit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/reachusama/ukaddresskit/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/ukaddresskit.svg)](https://pypi.org/project/ukaddresskit/)
[![Downloads](https://static.pepy.tech/badge/ukaddresskit)](https://pepy.tech/project/ukaddresskit)

[//]: # (<!-- Optional: Coverage &#40;Codecov&#41; -->)

[//]: # ([![codecov]&#40;https://codecov.io/gh/OWNER/REPO/branch/main/graph/badge.svg&#41;]&#40;https://codecov.io/gh/OWNER/REPO&#41;)

UK address utility based on machine learning and optimised search to parse, standardise, and compare addresses.

Address NER tagger is trained using crfsuite with help of 2 million uk housing addresses.

## Install - alpha stage

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

**Postcode Helpers**

```python
from ukaddresskit.postcode import *

normalize_postcode("sw1a2aa")  # "SW1A 2AA"
get_town("SW1A 2AA")      # "LONDON"
get_county("SW1A 2AA")         # "Greater London" (if in mapping)
get_county("SW1A 2AA") 
get_locality(postcode: str)
get_streets(postcode: str)
get_property_mix(postcode: str) -> Dict[str, float]

---

from ukaddresskit.locality import *

get_town_by_locality("Ab Kettleby")                 -> "MELTON MOWBRAY"
get_town_by_locality("Abberton", ambiguity="all")   -> ["COLCHESTER", "PERSHORE"]
list_towns_for_locality("Abberton")                 -> ["COLCHESTER", "PERSHORE"]
```

## Todo

- [x] Add outcode_to_county.csv into lookups
- [x] Fix bugs in library not loading on Colab
- [x] Create postcode fill utility
    - [x] get_town(postcode)
    - [x] get_county(postcode)
    - [x] get_locality(postcode)
    - [x] get_streets(postcode) → array of street names
    - [x] get_property_mix(postcode)
    - [x] add test cases
- [ ] Create address populate utility (add missing address components - town, county, etc)
- [ ] Create address linkage utility / comparing
- [ ] Define test cases, organise code
- [ ] Improve machine learning models
- [ ] Create .parquet sqlite storage, indexes for optimal searches
- [ ] 
  Create [online docs](https://medium.com/practical-coding/documenting-your-python-library-from-zero-to-website-488f87ae58f5)
- [ ] Improve Address Parser

**AddressParser (Pre & Post processing -- needs testing)**

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
