"""
convert_to_ebay.py
==================
Converts a Card Dealer Pro batch export CSV (input/) into an eBay AU
report-upload CSV (output/) ready for:
  https://www.ebay.com.au/sh/reports/uploads

Usage:
    python convert_to_ebay.py [input_file] [output_file]

If no arguments are given, default paths are used (see DEFAULT_* below).
"""

import csv
from datetime import datetime, time, timedelta, timezone
import os
import re
import sys

# ---------------------------------------------------------------------------
# Configuration – edit these to match your setup
# ---------------------------------------------------------------------------

DEFAULT_INPUT = r"input\batch-to-list.csv"
DEFAULT_OUTPUT = r"output\ebay_listings.csv"

# Listing schedule configuration
SCHEDULE_LISTINGS = True
SCHEDULE_TIME_AEST = "17:00"  # 24h format, e.g. 17:00 for 5:00 PM
LISTINGS_PER_DAY = 3

# Storage grouping tag is now entered at runtime and required.

# Fixed seller details
LOCATION     = "Parkes,NSW"
POSTAL_CODE  = "2870"
EBAY_CATEGORY = "261328"   # Sports Trading Cards (eBay AU)
DEFAULT_STORE_CATEGORY = "0"
BASKETBALL_STORE_CATEGORY = "24310696015"

SHIPPING_PROFILE = "Card Shipping - Standard Singles"
RETURN_PROFILE   = "Default return policy"
PAYMENT_PROFILE  = "Default Payment Policy"

# Safe default package size for card mailers (used by shipping policy setup)
PACKAGE_LENGTH_CM = 16
PACKAGE_WIDTH_CM = 11
PACKAGE_HEIGHT_CM = 1

# Mapping from card category → eBay league
SPORT_TO_LEAGUE = {
    "BASKETBALL": "NBA",
    "FOOTBALL":   "NFL",
    "BASEBALL":   "MLB",
    "HOCKEY":     "NHL",
    "SOCCER":     "Soccer",
}

# Condition string → (ConditionID, CardConditionID)
CONDITION_MAP = {
    "near mint or better": ("4000", "400010"),
    "excellent":           ("3000", "300010"),
    "very good":           ("2750", "275010"),
    "good":                ("2500", "250010"),
    "poor":                ("1000", "100010"),
}

# ---------------------------------------------------------------------------
# eBay output column order (must exactly match the template)
# ---------------------------------------------------------------------------

FIELD_HEADERS = [
    "*Action(SiteID=AU|Country=AU|Currency=AUD|Version=1193|CC=UTF-8)",
    "CustomLabel",
    "*Category",
    "StoreCategory",
    "*Title",
    "Subtitle",
    "Relationship",
    "*ConditionID",
    "*C:Graded",
    "*C:Sport",
    "*C:Player/Athlete",
    "*C:Parallel/Variety",
    "*C:Manufacturer",
    "C:Season",
    "*C:Features",
    "*C:Set",
    "CD:Grade - (ID: 27502)",
    "*C:League",
    "CD:Professional Grader - (ID: 27501)",
    "*C:Team",
    "*C:Autographed",
    "CD:Card Condition - (ID: 40001)",
    "*C:Card Name",
    "*C:Card Number",
    "CDA:Certification Number - (ID: 27503)",
    "*C:Type",
    "C:Signed By",
    "C:Autograph Authentication",
    "C:Year Manufactured",
    "C:Card Size",
    "C:Country/Region of Manufacturer",
    "C:Material",
    "C:Autograph Format",
    "C:Vintage",
    "C:Original/Licensed Reprint",
    "C:Event/Tournament",
    "C:Language",
    "C:Autograph Authentication Number",
    "C:Bundle Description",
    "C:California Prop 65 Warning",
    "C:Card Thickness",
    "C:Custom Bundle",
    "C:Insert Set",
    "C:Print Run",
    "PicURL",
    "GalleryType",
    "*Description",
    "*Format",
    "*Duration",
    "*StartPrice",
    "BuyItNowPrice",
    "*Quantity",
    "PayPalAccepted",
    "PayPalEmailAddress",
    "ImmediatePayRequired",
    "PaymentInstructions",
    "*Location",
    "PostalCode",
    "ShippingType",
    "ShippingService-1:Option",
    "ShippingService-1:FreeShipping",
    "ShippingService-1:Cost",
    "ShippingService-1:AdditionalCost",
    "ShippingService-2:Option",
    "ShippingService-2:Cost",
    "*DispatchTimeMax",
    "PromotionalShippingDiscount",
    "ShippingDiscountProfileID",
    "*ReturnsAcceptedOption",
    "ReturnsWithinOption",
    "RefundOption",
    "ShippingCostPaidByOption",
    "AdditionalDetails",
    "ShippingProfileName",
    "ReturnProfileName",
    "PaymentProfileName",
    "TakeBackPolicyID",
    "ProductCompliancePolicyID",
    "ScheduleTime",
    "BestOfferEnabled",
    "MinimumBestOfferPrice",
    "BestOfferAutoAcceptPrice",
    "*C:Rookie",
    "*C:Memorabilia",
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def parse_attrs(row):
    """Return a set of attribute tokens (e.g. {'AU', 'SN', 'MEM', 'RC'})."""
    raw = row.get("attributes", "")
    return {a.strip().upper() for a in raw.split(",") if a.strip()}


def map_condition(condition_str):
    """Return (ConditionID, CardConditionID) tuple."""
    key = condition_str.strip().lower()
    for pattern, ids in CONDITION_MAP.items():
        if pattern in key:
            return ids
    return ("4000", "400010")  # fallback: Near Mint or Better


def build_features(row, attrs):
    """
    Build a pipe-separated eBay *C:Features string using eBay AU accepted values.

    Attribute-based (from the input 'attributes' column):
      RC  → Rookie Card
      AU  → Autograph
      MEM → Memorabilia
      SN  → Serial Numbered

    Text-based (scanned from title + subset for common card features):
      Die Cut, Refractor, Insert, Short Print, Jersey, Patch, Prizm,
      Shimmer, Holo, Optic, Cracked Ice, First Edition / 1st Edition,
      Auto (as alternative autograph spelling), Press Proof
    """
    features = []

    # --- attribute-code mappings ---
    if "RC" in attrs or "Rookie" in row.get("title", ""):
        features.append("RC")
    if "AU" in attrs:
        features.append("Autograph")
    if "MEM" in attrs:
        features.append("Memorabilia")
    if "SN" in attrs:
        features.append("Serial Numbered")

    # --- keyword detection from title and subset ---
    haystack = " ".join([
        row.get("title", ""),
        row.get("subset", ""),
    ]).lower()

    TEXT_FEATURES = [
        ("die cut",        "Die Cut"),
        ("refractor",      "Refractor"),
        ("short print",    "Short Print"),
        (" sp ",           "Short Print"),
        ("jersey",         "Jersey"),
        ("patch",          "Patch"),
        ("prizm",          "Prizm"),
        ("shimmer",        "Shimmer"),
        ("holo",           "Holo"),
        ("cracked ice",    "Cracked Ice"),
        ("first edition",  "1st Edition"),
        ("1st edition",    "1st Edition"),
        ("press proof",    "Press Proof"),
        ("insert",         "Insert"),
    ]

    for keyword, label in TEXT_FEATURES:
        if keyword in haystack and label not in features:
            features.append(label)

    return "|".join(features)


def extract_print_run(title):
    """
    Parse a serial-number print run from the title.
    Looks for patterns like '30/49', '128/149', '246/249'.
    Returns the denominator string (e.g. '49') or empty string.
    """
    import re
    match = re.search(r'\b\d+/(\d+)\b', title)
    return match.group(1) if match else ""


def build_subtitle(row, attrs, print_run):
    """
    Build a concise subtitle (max 55 chars) shown in eBay search results.
    Format: {condition short} | {badge} | {serial info}
    """
    parts = []

    cond = row.get("condition", "").strip()
    if cond:
        parts.append(cond)

    badges = []
    if "RC" in attrs or "Rookie" in row.get("title", ""):
        badges.append("RC")
    if "AU" in attrs:
        badges.append("Auto")
    if "MEM" in attrs:
        badges.append("Mem")
    if "SN" in attrs and print_run:
        badges.append(f"#{print_run}")
    elif "SN" in attrs:
        badges.append("SN")
    if badges:
        parts.append(" ".join(badges))

    subtitle = " | ".join(parts)
    return subtitle[:55]


def parse_price(value):
    """Parse a sale price string and return float, or None if invalid."""
    text = str(value or "").strip()
    if not text:
        return None

    # Keep digits, minus sign, and decimal point for common CSV price formats.
    cleaned = re.sub(r"[^\d.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_schedule_time(time_str):
    """Parse HH:MM and return (hour, minute)."""
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid SCHEDULE_TIME_AEST value: {time_str}")

    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid SCHEDULE_TIME_AEST value: {time_str}")

    return hour, minute


def build_schedule_times(total_rows, listings_per_day, hour, minute):
    """
    Build per-row schedule timestamps from an AEST target time.

    Rows are grouped by day using listings_per_day. Each day gets the same
    activation time (hour:minute).

    eBay bulk upload may interpret ScheduleTime as UTC. To ensure listings
    go live at the intended AEST time, this function converts each AEST target
    datetime into a UTC timestamp string.
    """
    if total_rows <= 0:
        return []

    if listings_per_day < 1:
        listings_per_day = 1

    aest = timezone(timedelta(hours=10), name="AEST")
    now_aest = datetime.now(timezone.utc).astimezone(aest)

    start_date = now_aest.date()
    target_today = datetime.combine(start_date, time(hour, minute), tzinfo=aest)
    if now_aest >= target_today:
        start_date = start_date + timedelta(days=1)

    scheduled = []
    for idx in range(total_rows):
        day_offset = idx // listings_per_day
        day = start_date + timedelta(days=day_offset)
        schedule_dt_aest = datetime.combine(day, time(hour, minute), tzinfo=aest)
        schedule_dt_utc = schedule_dt_aest.astimezone(timezone.utc)
        scheduled.append(schedule_dt_utc.strftime("%Y-%m-%d %H:%M:%S"))

    return scheduled


def prompt_group_tag():
    """Prompt for required storage section tag in terminal (e.g. AB5)."""
    while True:
        entered = input("Enter storage section tag (required, e.g. AB5): ").strip().upper()
        if entered:
            return entered
        print("Section tag is required.")


def confirm_run(group_tag, total_rows):
    """Ask for a yes/no confirmation before writing output CSV."""
    group_text = group_tag or "(none)"
    print("\nReady to generate eBay upload CSV with:")
    print(f"- Listings: {total_rows}")
    print(f"- Group tag: {group_text}")
    print(f"- Group note: {'Group: ' + group_tag if group_tag else '(none)'}")
    print(f"- Label prefix: {group_tag + '-' if group_tag else '(none)'}")
    print(
        "- Package size target (shipping policy): "
        f"{PACKAGE_LENGTH_CM} x {PACKAGE_WIDTH_CM} x {PACKAGE_HEIGHT_CM} cm"
    )
    answer = input("Proceed? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def convert_row(row, group_tag=""):
    """Map one input CSV row to one eBay output CSV row (as a dict)."""
    attrs      = parse_attrs(row)
    is_graded  = row.get("graded", "").strip().lower() == "yes"
    is_auto    = "AU" in attrs
    is_rookie  = "Rookie" in row.get("title", "") or "RC" in attrs
    is_mem     = "MEM" in attrs

    condition_id, card_condition = map_condition(row.get("condition", ""))
    category = row.get("category", "").strip().upper()
    league = SPORT_TO_LEAGUE.get(category, "")
    store_category = (
        BASKETBALL_STORE_CATEGORY
        if category == "BASKETBALL"
        else DEFAULT_STORE_CATEGORY
    )

    front = row.get("front_image", "").strip()
    back  = row.get("back_image", "").strip()
    pic_url = f"{front} | {back}" if front and back else front or back

    sale_price_raw = row.get("sale_price", "")
    sale_price_value = parse_price(sale_price_raw)
    best_offer_enabled = "1" if sale_price_value is not None and sale_price_value > 10 else "0"

    print_run = extract_print_run(row.get("title", ""))
    subtitle  = build_subtitle(row, attrs, print_run)

    return {
        "*Action(SiteID=AU|Country=AU|Currency=AUD|Version=1193|CC=UTF-8)": "Add",
        "CustomLabel":                              f"{group_tag}-{row.get('sku', '')}" if group_tag else row.get("sku", ""),
        "*Category":                                EBAY_CATEGORY,
        "StoreCategory":                            store_category,
        "*Title":                                   row.get("title", ""),
        "Subtitle":                                 "",
        "Relationship":                             "",
        "*ConditionID":                             condition_id,
        "*C:Graded":                                "Yes" if is_graded else "No",
        "*C:Sport":                                 row.get("category", ""),
        "*C:Player/Athlete":                        row.get("player", ""),
        "*C:Parallel/Variety":                      row.get("subset", ""),
        "*C:Manufacturer":                          row.get("brand", ""),
        "C:Season":                                 row.get("year", ""),
        "*C:Features":                              build_features(row, attrs),
        "*C:Set":                                   row.get("set", ""),
        "CD:Grade - (ID: 27502)":                   row.get("grade_name", "") if is_graded else "",
        "*C:League":                                league,
        "CD:Professional Grader - (ID: 27501)":     row.get("grader", "") if is_graded else "",
        "*C:Team":                                  row.get("team", ""),
        "*C:Autographed":                           "Yes" if is_auto else "No",
        "CD:Card Condition - (ID: 40001)":          card_condition,
        "*C:Card Name":                             row.get("player", ""),
        "*C:Card Number":                           row.get("card_number", ""),
        "CDA:Certification Number - (ID: 27503)":   row.get("certification_number", "") if is_graded else "",
        "*C:Type":                                  "Sports Trading Card",
        "C:Signed By":                              "",
        "C:Autograph Authentication":               "",
        "C:Year Manufactured":                      row.get("year", ""),
        "C:Card Size":                              "",
        "C:Country/Region of Manufacturer":         "",
        "C:Material":                               "",
        "C:Autograph Format":                       "",
        "C:Vintage":                                "",
        "C:Original/Licensed Reprint":              "",
        "C:Event/Tournament":                       "",
        "C:Language":                               "",
        "C:Autograph Authentication Number":        "",
        "C:Bundle Description":                     "",
        "C:California Prop 65 Warning":             "",
        "C:Card Thickness":                         "",
        "C:Custom Bundle":                          "",
        "C:Insert Set":                             row.get("subset", ""),
        "C:Print Run":                              print_run,
        "PicURL":                                   pic_url,
        "GalleryType":                              "",
        "*Description":                             row.get("description", ""),
        "*Format":                                  "FixedPrice",
        "*Duration":                                "GTC",
        "*StartPrice":                              sale_price_raw,
        "BuyItNowPrice":                            "",
        "*Quantity":                                "1",
        "PayPalAccepted":                           "0",
        "PayPalEmailAddress":                       "",
        "ImmediatePayRequired":                     "1",
        "PaymentInstructions":                      "",
        "*Location":                                LOCATION,
        "PostalCode":                               POSTAL_CODE,
        "ShippingType":                             "",
        "ShippingService-1:Option":                 "",
        "ShippingService-1:FreeShipping":           "",
        "ShippingService-1:Cost":                   "",
        "ShippingService-1:AdditionalCost":         "",
        "ShippingService-2:Option":                 "",
        "ShippingService-2:Cost":                   "",
        "*DispatchTimeMax":                         "0",
        "PromotionalShippingDiscount":              "",
        "ShippingDiscountProfileID":                "",
        "*ReturnsAcceptedOption":                   "ReturnsAccepted",
        "ReturnsWithinOption":                      "Days_14",
        "RefundOption":                             "MoneyBackOrReplacement",
        "ShippingCostPaidByOption":                 "Buyer",
        "AdditionalDetails":                        f"Group: {group_tag}" if group_tag else "",
        "ShippingProfileName":                      SHIPPING_PROFILE,
        "ReturnProfileName":                        RETURN_PROFILE,
        "PaymentProfileName":                       PAYMENT_PROFILE,
        "TakeBackPolicyID":                         "",
        "ProductCompliancePolicyID":                "",
        "ScheduleTime":                             "",
        "BestOfferEnabled":                         best_offer_enabled,
        "MinimumBestOfferPrice":                    "",
        "BestOfferAutoAcceptPrice":                 "",
        "*C:Rookie":                                "Yes" if is_rookie else "No",
        "*C:Memorabilia":                           "Yes" if is_mem else "No",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Resolve paths relative to this script's directory
    base = os.path.dirname(os.path.abspath(__file__))

    input_file  = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, DEFAULT_INPUT)
    output_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(base, DEFAULT_OUTPUT)

    if not os.path.isfile(input_file):
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    try:
        group_tag = prompt_group_tag()
    except EOFError:
        print("ERROR: Section tag is required and no terminal input was provided.")
        sys.exit(1)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(input_file, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)

    try:
        if not confirm_run(group_tag, len(rows)):
            print("Cancelled. No output file was written.")
            sys.exit(0)
    except EOFError:
        # Non-interactive run: proceed without confirmation prompt.
        pass

    schedule_times = []
    if SCHEDULE_LISTINGS:
        hour, minute = parse_schedule_time(SCHEDULE_TIME_AEST)
        schedule_times = build_schedule_times(
            total_rows=len(rows),
            listings_per_day=LISTINGS_PER_DAY,
            hour=hour,
            minute=minute,
        )

    num_cols = len(FIELD_HEADERS)
    info_row = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_AU"] + [""] * (num_cols - 3)

    with open(output_file, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(info_row)
        writer.writerow(FIELD_HEADERS)
        for idx, row in enumerate(rows):
            mapped = convert_row(row, group_tag=group_tag)
            if schedule_times:
                mapped["ScheduleTime"] = schedule_times[idx]
            writer.writerow([mapped.get(h, "") for h in FIELD_HEADERS])

    print(f"Done! Converted {len(rows)} card(s) → {output_file}")
    if schedule_times:
        print(
            f"Scheduled at {SCHEDULE_TIME_AEST} AEST, "
            f"{LISTINGS_PER_DAY} listing(s) per day."
        )
    print(
        "Package size target: "
        f"{PACKAGE_LENGTH_CM} x {PACKAGE_WIDTH_CM} x {PACKAGE_HEIGHT_CM} cm"
    )
    if group_tag:
        print(f"Applied group tag: {group_tag}")


if __name__ == "__main__":
    main()
