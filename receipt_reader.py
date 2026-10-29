import glob
import re
from datetime import datetime
from PIL import Image, ImageOps
import pytesseract
from classifier import classify_bill

try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Pillow open HEIC photos from iPhones
except ImportError:
    pass

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff",
    ".webp", ".heic", ".heif",
)

TOLERANCE = 1.0  # allow up to 1 rupee difference for round-off

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_PATTERNS = [
    (r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?!\d)", "numeric"),   # 09/09/2026
    (r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", "iso"),                    # 2026-09-09
    (r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})(?!\d)", "numeric"),  # 09/09/26
    (r"(\d{1,2})(?:st|nd|rd|th)?[\s\-,]+([A-Za-z]{3,9})\.?[\s\-,]+(\d{4})", "day_month"),  # 14th Feb 2025
    (r"([A-Za-z]{3,9})\.?[\s\-]+(\d{1,2})(?:st|nd|rd|th)?,?[\s\-]+(\d{4})", "month_day"),  # Feb 14, 2025
]

# Words that label the final amount. "Subtotal" and "Total Items" are excluded.
TOTAL_LABEL = (
    r"(?:grand\s*total|net\s*(?:amt|amount|payable)|amount\s*(?:payable|to\s*pay|due)"
    r"|bill\s*amount|total\s*amount|(?<!sub)(?<!sub\s)\btotal\b(?!\s*items))"
)

# Header lines that are not the shop name
SHOP_SKIP = re.compile(
    r"\b(gstin|bill|date|counter|ph|phone|mob|cashier|order|fssai|lic|invoice|"
    r"receipt|thank|welcome|paid|tax|cash)\b",
    re.IGNORECASE,
)


def load_image(path):
    # Opens any supported image, fixes phone rotation, removes transparency,
    # and returns a grayscale image that OCR reads well.
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)  # fixes photos that are turned sideways
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])  # white behind transparent areas
        image = background
    return image.convert("L")


def read_text(image_path):
    return pytesseract.image_to_string(load_image(image_path))


def _make_date(day, month, year):
    # Returns dd-mm-yyyy if the parts form a real date, otherwise None
    if month is None:
        return None
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return datetime(year, int(month), int(day)).strftime("%d-%m-%Y")
    except ValueError:
        return None


def find_date(text):
    # Returns the first valid date as dd-mm-yyyy, or None if the bill prints no date
    for pattern, kind in DATE_PATTERNS:
        for m in re.finditer(pattern, text):
            if kind == "numeric":
                result = _make_date(m.group(1), m.group(2), m.group(3))
            elif kind == "iso":
                result = _make_date(m.group(3), m.group(2), m.group(1))
            elif kind == "day_month":
                result = _make_date(m.group(1), MONTHS.get(m.group(2)[:3].lower()), m.group(3))
            else:  # month_day
                result = _make_date(m.group(2), MONTHS.get(m.group(1)[:3].lower()), m.group(3))
            if result:
                return result
    return None


def find_total(text):
    # Matches NetAmt, Total Amount, Grand Total, Amount Payable, or a plain "Total ₹537.00"
    match = re.search(
        TOTAL_LABEL + r"[^\d\n]*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def find_subtotal(text):
    # Matches "Subtotal 310.00" or "Gross Amt 1386.53"
    match = re.search(
        r"(?:sub\s*total|gross\s*amt)[^\d\n]*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def find_shop(text):
    # Take the first line that looks like a shop name, skipping header lines
    for line in text.splitlines():
        if SHOP_SKIP.search(line):
            continue
        cleaned = re.sub(r"[^A-Za-z' ]", " ", line)
        words = [w for w in cleaned.split() if len(w) >= 2]
        name = " ".join(words)
        if len(re.findall(r"[A-Za-z]", name)) >= 5:
            return name
    return None


def item_amounts(text):
    # Keep lines that end with a money amount like 120.00,
    # skipping totals, taxes, and fees such as packaging, delivery, and promo.
    skip_pattern = (
        r"\b(total|subtotal|gross|discount|gst|cgst|sgst|igst|tax|taxes|round|"
        r"netamt|net amt|bill|date|gstin|items|packaging|charges|delivery|"
        r"fee|promo|service|tip|cash|change|paid)\b"
    )
    amounts = []
    for line in text.splitlines():
        if re.search(skip_pattern, line, re.IGNORECASE):
            continue
        match = re.search(r"(\d+\.\d{2})\s*$", line)
        if match:
            amounts.append(float(match.group(1)))
    return amounts


def check_items(text):
    # Compare the item sum with the printed subtotal. Bills without a
    # subtotal are marked for manual checking instead of being wrongly flagged.
    items = item_amounts(text)
    items_sum = round(sum(items), 2)
    subtotal = find_subtotal(text)
    if subtotal is None:
        return items_sum, find_total(text), "UNKNOWN - no subtotal printed, check the total yourself"
    if abs(items_sum - subtotal) <= TOLERANCE:
        return items_sum, subtotal, "OK"
    return items_sum, subtotal, "MISMATCH - check this receipt"


def is_supported_image(filename):
    return filename.lower().endswith(IMAGE_EXTENSIONS)


if __name__ == "__main__":
    receipt_files = sorted(f for f in glob.glob("*") if is_supported_image(f))

    if not receipt_files:
        print("No receipt photos found in this folder.")

    for file in receipt_files:
        try:
            text = read_text(file)
        except Exception as error:
            print(f"--- {file} ---")
            print("Could not read this image:", error)
            print()
            continue
        shop = find_shop(text) or ""
        category, reason = classify_bill(shop, text)
        items_sum, expected, status = check_items(text)
        print(f"--- {file} ---")
        print("Shop:", shop or None)
        print("Date:", find_date(text))
        print("Total:", find_total(text))
        print("Category:", category, f"({reason})")
        print("Items sum:", items_sum)
        print("Expected:", expected)
        print("Check:", status)
        print()