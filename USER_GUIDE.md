# eBay AU CSV Converter — User Guide

Converts a Card Dealer Pro batch export into an eBay AU report-upload CSV.

---

## Quick Start

1. Export your batch from Card Dealer Pro and save it to the `input/` folder.
2. Rename (or set) the file to `batch-to-list.csv` — or pass the filename as an argument (see below).
3. Run the script:

```powershell
cd "c:\Users\Neil_\OneDrive\Documents\card sale\CSV processing"
python convert_to_ebay.py
```

4. Your upload file is created at `output\ebay_listings.csv`.
5. Go to [https://www.ebay.com.au/sh/reports/uploads](https://www.ebay.com.au/sh/reports/uploads) and upload it.

---

## Using a Different Input File

Pass the input path as an argument:

```powershell
python convert_to_ebay.py "input\my-batch.csv"
```

Or permanently change the default at the top of `convert_to_ebay.py`:

```python
DEFAULT_INPUT = r"input\my-batch.csv"
```

---

## What Gets Mapped

| Input (Card Dealer Pro)   | Output (eBay field)          |
|---------------------------|------------------------------|
| `title`                   | `*Title`                     |
| `description`             | `*Description`               |
| `sale_price`              | `*StartPrice`                |
| `player`                  | `*C:Player/Athlete`, `*C:Card Name` |
| `team`                    | `*C:Team`                    |
| `brand`                   | `*C:Manufacturer`            |
| `set`                     | `*C:Set`                     |
| `subset`                  | `*C:Parallel/Variety`, `C:Insert Set` |
| `year`                    | `C:Season`, `C:Year Manufactured` |
| `card_number`             | `*C:Card Number`             |
| `condition`               | `*ConditionID`, `CD:Card Condition` |
| `category`                | `*C:Sport`, `*C:League`      |
| `attributes`              | `*C:Features`, `*C:Autographed`, `*C:Rookie`, `*C:Memorabilia` |
| `front_image` + `back_image` | `PicURL`                  |
| `sku`                     | `CustomLabel`                |

---

## Attributes Column

The `attributes` column in Card Dealer Pro uses comma-separated codes that the script automatically translates:

| Code  | eBay meaning         |
|-------|----------------------|
| `RC`  | Rookie Card          |
| `AU`  | Autograph            |
| `MEM` | Memorabilia          |
| `SN`  | Serial Numbered      |

The script also scans the title/subset text for keywords like `Holo`, `Refractor`, `Prizm`, `Die Cut`, `Patch`, `Jersey`, `Short Print`, etc. and adds them to `*C:Features`.

---

## Serial Numbers / Print Run

If the title contains a serial number like `30/49`, the denominator (`49`) is automatically written to the `C:Print Run` field.

---

## Fixed Seller Settings

These are set at the top of `convert_to_ebay.py` and apply to every listing:

| Setting             | Value                          |
|---------------------|--------------------------------|
| Location            | Parkes, NSW                    |
| Postcode            | 2870                           |
| eBay Category       | 261328 (Sports Trading Cards)  |
| Shipping Profile    | Card Shipping - Standard Singles |
| Return Profile      | Default return policy          |
| Payment Profile     | Default Payment Policy         |
| Best Offer          | Enabled                        |
| Returns             | 14 days, Money Back or Replacement |

To change any of these, edit the constants near the top of the script.

---

## Condition Mapping

| Card Dealer Pro condition | eBay Condition ID |
|---------------------------|-------------------|
| Near Mint or Better       | 4000              |
| Excellent                 | 3000              |
| Very Good                 | 2750              |
| Good                      | 2500              |
| Poor                      | 1000              |

---

## Setting Up the Environment (First Time / After Cloning)

The `.venv` folder is not stored in git. To recreate it:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Note:** If you see `No Python at '...'` when running the script, the venv is broken (e.g. Python was upgraded). Delete `.venv` and repeat the steps above.

---

## Market Price Check Script

Use `check_ebay_prices.py` to compare your listing prices against the cheapest competing eBay listings.

### 1) Configure API keys and settings

1. Open `price_check_config.json`.
2. Set these values:
	- `ebay.client_id`
	- `ebay.client_secret`
	- `ebay.seller_username`
3. Optional: tune search filters like `search.price_max`, `search.result_limit`, and `search.ignore_words`.

> `price_check_config.json` is ignored by git so your secrets stay local.

### 2) Input file format

By default, the checker reads `output\ebay_listings.csv` and uses:
- `*Title` as the card title
- `*StartPrice` as your price

It also supports a simple custom CSV with columns:
- `title`
- `my_price`

### 3) Run it

```powershell
python check_ebay_prices.py
```

Optional arguments:

```powershell
python check_ebay_prices.py [input_csv] [output_csv] [config_json]
```

Example:

```powershell
python check_ebay_prices.py "output\ebay_listings.csv" "output\my_price_report.csv" "price_check_config.json"
```

### 4) Output

A report is written to `output\ebay_price_check_YYYY-MM-DD.csv` (or your custom output path) with:
- Date
- Card Title
- My Price
- Cheapest Comp Total (item + shipping)
- Difference
- Status (`OVERPRICED`, `COMPETITIVE`, or `NO COMP FOUND`)
- Comp Link

---

## Git — What Is and Isn't Tracked

| Tracked                  | Ignored                        |
|--------------------------|--------------------------------|
| `input\batch-to-list.csv`| `.venv\`                       |
| `requirements.txt`       | `*.py`                         |
| `USER_GUIDE.md`          | `output\ebay_listings.csv`     |
| `.gitignore`             | `__pycache__\`, `*.pyc`        |

Python source files (`*.py`) are excluded from git. If you need to version-control the script, remove the `*.py` line from `.gitignore`.

---

## Typical Batch Workflow

```powershell
# 0. Activate the venv (once per terminal session)
.\.venv\Scripts\Activate.ps1

# 1. Run the converter
python convert_to_ebay.py

# 2. Commit and push to GitHub
git add -A
git commit -m "Add batch XXXXXX"
git push
```
