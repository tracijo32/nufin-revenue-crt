### NU-ARD Stripe Revenue Daily Reconciliation

Author: Traci Johnson

#### Overview
This code automates the process of balancing the wire transfers of revenue from Stripe with the internal accounting provided on ARD's internal Salesforce data warehouse - CatConnect.

For more details, see the [documentation](docs.md) file in this repo.

Future developers should read the [developer notes](dev_notes.md).

#### Installation instructions
This project requires Python 3.10 or later. From the repo root, create a virtual environment (optional but recommended), then install the dependencies:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The pipeline lives in `src/` and is run from that folder. Pass the path to a working directory that contains `input/` (config CSVs) and `reports/` (Blackthorn, membership, and Stripe files). Output is written to `output/` in that same directory.

```
cd src
python main.py C:\path\to\your\working\directory
```

