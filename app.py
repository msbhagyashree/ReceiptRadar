import csv
import os
import re
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

from receipt_reader import (
    IMAGE_EXTENSIONS, is_supported_image, read_text, find_date, find_total,
    find_shop, check_items,
)
from classifier import classify_bill, remember_shop, category_names

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # largest upload: 25 MB (phone photos)

UPLOAD_FOLDER = "uploads"
EXPENSE_FILE = "expenses.csv"
INCOME_FILE = "income.csv"
EXPENSE_FIELDS = ["date", "shop", "category", "amount"]
INCOME_FIELDS = ["month", "source", "amount"]
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def to_iso_date(text):
    # Accepts 09-09-2026, 09/09/2026, 09-09-26, or 2026-09-09
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_csv(path, fields, row):
    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


@app.errorhandler(413)
def file_too_large(_error):
    return render_template("index.html", error="That photo is larger than 25 MB. Try a smaller photo."), 413


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    photo = request.files.get("receipt")
    if photo is None or photo.filename == "":
        return render_template("index.html", error="Please take or choose a photo first.")

    if not is_supported_image(photo.filename):
        return render_template(
            "index.html",
            error="That file type isn't supported. Choose a photo: JPG, PNG, WEBP, BMP, GIF, TIFF, or HEIC.",
        )

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = os.path.join(UPLOAD_FOLDER, f"{stamp}_{secure_filename(photo.filename)}")
    photo.save(path)

    try:
        text = read_text(path)
    except Exception:
        return render_template(
            "index.html",
            error="Could not read this image. It may be damaged, or it's a HEIC photo and HEIC support isn't installed (run: pip install pillow-heif).",
        )

    shop = find_shop(text) or ""
    category, _reason = classify_bill(shop, text)
    items_sum, expected, status = check_items(text)
    return render_template(
        "confirm.html",
        date=find_date(text) or "",
        shop=shop,
        total=find_total(text),
        items_sum=items_sum,
        expected=expected,
        status=status,
        text=text,
        categories=category_names(),
        suggested=category,
    )


@app.route("/save", methods=["POST"])
def save():
    iso_date = to_iso_date(request.form.get("date", ""))
    if iso_date is None:
        return render_template(
            "index.html",
            error="Date not recognized. Use dd-mm-yyyy, for example 09-09-2026.",
        )

    shop = request.form.get("shop", "").strip() or "Unknown shop"
    category = request.form.get("category") or "Other"
    try:
        amount = round(float(request.form.get("amount", "")), 2)
    except ValueError:
        return render_template("index.html", error="The amount must be a number.")

    # Remember the category for this shop, so the same shop is classified the same way next time
    if shop != "Unknown shop":
        remember_shop(shop, category)

    append_csv(EXPENSE_FILE, EXPENSE_FIELDS, {
        "date": iso_date,
        "shop": shop,
        "category": category,
        "amount": amount,
    })
    return redirect(url_for("dashboard", month=iso_date[:7], message="Bill saved."))


@app.route("/income", methods=["POST"])
def add_income():
    month = request.form.get("month", "")
    source = request.form.get("source", "").strip() or "Pocket money"
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        return redirect(url_for("dashboard", error="Choose a valid month."))
    try:
        amount = round(float(request.form.get("amount", "")), 2)
    except ValueError:
        return redirect(url_for("dashboard", month=month, error="Enter a valid amount."))

    append_csv(INCOME_FILE, INCOME_FIELDS, {"month": month, "source": source, "amount": amount})
    return redirect(url_for("dashboard", month=month, message=f"Saved ₹{amount:.2f} as {source}."))


@app.route("/dashboard")
def dashboard():
    month = request.args.get("month", "")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        month = datetime.now().strftime("%Y-%m")

    expenses = []
    for r in read_csv(EXPENSE_FILE):
        if r["date"].startswith(month):
            r["amount"] = float(r["amount"])
            expenses.append(r)

    incomes = []
    for r in read_csv(INCOME_FILE):
        if r["month"] == month:
            r["amount"] = float(r["amount"])
            incomes.append(r)

    total_income = round(sum(r["amount"] for r in incomes), 2)
    total_spent = round(sum(r["amount"] for r in expenses), 2)
    saved = round(total_income - total_spent, 2)

    by_category = {}
    by_day = {}
    for r in expenses:
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]
        by_day[r["date"]] = by_day.get(r["date"], 0) + r["amount"]

    category_totals = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    day_totals = sorted(by_day.items())
    top_category = category_totals[0][0] if category_totals else None

    return render_template(
        "dashboard.html",
        month=month,
        expenses=expenses,
        incomes=incomes,
        total_income=total_income,
        total_spent=total_spent,
        saved=saved,
        category_totals=category_totals,
        day_totals=day_totals,
        top_category=top_category,
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)