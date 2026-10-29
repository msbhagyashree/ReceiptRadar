# ReceiptRadar

Scan a photo of a shop bill, and ReceiptRadar reads the shop name, date, and total, suggests a spending category, and tracks your income and savings for each month. It runs as a Flask web app on your own computer, so your receipts stay private.

## Features

- Upload a bill photo from your phone or laptop (JPG, PNG, WEBP, BMP, GIF, TIFF, and HEIC)
- OCR with Tesseract reads the shop name, date, and total
- Date detection for many formats, including `09/09/2026`, `14th Feb 2025`, and `Feb 14, 2025`
- Category suggestion from the shop name, or from item names on the bill
- Your corrections are remembered for the same shop next time
- Check that the item amounts add up to the printed subtotal, and flag mismatches
- Monthly dashboard with income, spending, savings, and a spending meter

## How the Classifier Works

1. Shops you've already corrected (saved in `learned.json`)
2. Shop names in `categories.json` (for example, "mart" → Groceries)
3. Item names on the bill (at least two matching keywords needed)
4. Otherwise, the category is set to Other, and you choose it

To teach the app a new shop or product, add it to `categories.json`. No restart is needed.

## Setup

1. Install Tesseract OCR for Windows from the UB Mannheim build on GitHub.
2. Install the Python packages:

   ```
   pip install flask pytesseract pillow pillow-heif pypdf
   ```

3. Check the Tesseract path in `receipt_reader.py` matches your install folder.
4. Run the app:

   ```
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

To use it on your phone, connect both devices to the same Wi-Fi, then open `http://YOUR-LAPTOP-IP:5000`.

## Test Results

| Bill | Date | Total | Category | Item check |
|---|---|---|---|---|
| Hari's Mart (real paper bill) | 09-09-2026 | 1387 | Groceries | MISMATCH (a rate printed incorrectly on the bill) |
| Sri Balaji Stores (test bill) | 15-11-2026 | 325.50 | Groceries | OK |
| Green Valley Mart (test bill) | 22-11-2026 | 360.00 | Groceries | OK |
| Zomato delivery bill | 14-02-2025 | 537 | Food | UNKNOWN (no subtotal printed) |

*Add more real bills here as you test them.*

## Known Limitations

- OCR misreads some letters, such as "Hari's" being read as "ari's", so shop names need checking.
- Delivery bills with fees and promo lines can't be fully verified.
- Bills that print no date need the date typed in manually.
- Runs on one computer and needs Wi-Fi for phone use. There's no cloud sync.
- The app isn't a substitute for a bank statement or tax advice.

## Next Steps

- Read fee and promo lines so delivery bills can be verified
- Support mixed English and Tamil receipts
- Export monthly summaries as CSV or PDF
- Host it online with a login for each user

## Project Structure

```
PROJECT - 2/
├── app.py               # Flask routes and pages
├── receipt_reader.py    # OCR, date, total, and item check
├── classifier.py        # category rules and learning
├── categories.json      # shop and item keywords (editable)
├── templates/           # HTML pages
└── static/              # CSS and icon
