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
import os
import sys

# ---------------------------------------------------------------------------
# Configuration – edit these to match your setup
# ---------------------------------------------------------------------------

DEFAULT_INPUT = r"input\batch-941678-export (2).csv"
DEFAULT_OUTPUT = r"output\ebay_listings.csv"

# Fixed seller details
LOCATION     = "Parkes,NSW"
POSTAL_CODE  = "2870"
EBAY_CATEGORY = "261328"   # Sports Trading Cards (eBay AU)

SHIPPING_PROFILE = "Card Shipping - Standard Singles"
RETURN_PROFILE   = "Default return policy"
PAYMENT_PROFILE  = "Default Payment Policy"

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


def convert_row(row):
    """Map one input CSV row to one eBay output CSV row (as a dict)."""
    attrs      = parse_attrs(row)
    is_graded  = row.get("graded", "").strip().lower() == "yes"
    is_auto    = "AU" in attrs
    is_rookie  = "Rookie" in row.get("title", "") or "RC" in attrs
    is_mem     = "MEM" in attrs

    condition_id, card_condition = map_condition(row.get("condition", ""))
    league = SPORT_TO_LEAGUE.get(row.get("category", "").strip().upper(), "")

    front = row.get("front_image", "").strip()
    back  = row.get("back_image", "").strip()
    pic_url = f"{front} | {back}" if front and back else front or back

    print_run = extract_print_run(row.get("title", ""))
    subtitle  = build_subtitle(row, attrs, print_run)

    return {
        "*Action(SiteID=AU|Country=AU|Currency=AUD|Version=1193|CC=UTF-8)": "Add",
        "CustomLabel":                              row.get("sku", ""),
        "*Category":                                EBAY_CATEGORY,
        "StoreCategory":                            "0",
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
        "*StartPrice":                              row.get("sale_price", ""),
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
        "AdditionalDetails":                        "",
        "ShippingProfileName":                      SHIPPING_PROFILE,
        "ReturnProfileName":                        RETURN_PROFILE,
        "PaymentProfileName":                       PAYMENT_PROFILE,
        "TakeBackPolicyID":                         "",
        "ProductCompliancePolicyID":                "",
        "ScheduleTime":                             "",
        "BestOfferEnabled":                         "1",
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

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(input_file, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)

    num_cols = len(FIELD_HEADERS)
    info_row = ["Info", "Version=1.0.0", "Template=fx_category_template_EBAY_AU"] + [""] * (num_cols - 3)

    with open(output_file, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(info_row)
        writer.writerow(FIELD_HEADERS)
        for row in rows:
            mapped = convert_row(row)
            writer.writerow([mapped.get(h, "") for h in FIELD_HEADERS])

    print(f"Done! Converted {len(rows)} card(s) → {output_file}")


if __name__ == "__main__":
    main()
