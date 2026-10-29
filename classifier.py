import json
import os
import re
from difflib import SequenceMatcher

DB_FILE = "categories.json"      # the database you edit
LEARNED_FILE = "learned.json"    # shops you have confirmed (created automatically)
DEFAULT_CATEGORY = "Other"
MIN_ITEM_HITS = 2                # item keywords needed before trusting the items


def _squash(text):
    # "Pothy's Silks" -> "pothyssilks", so spaces, dots and apostrophes don't matter
    return re.sub(r"[^a-z]", "", text.lower())


def load_db():
    with open(DB_FILE, encoding="utf-8") as f:
        return json.load(f)["categories"]


def load_learned():
    if not os.path.exists(LEARNED_FILE):
        return {}
    with open(LEARNED_FILE, encoding="utf-8") as f:
        return json.load(f)


def remember_shop(shop, category):
    # Called when you save a bill, so the same shop is classified the same way next time
    learned = load_learned()
    learned[_squash(shop)] = category
    with open(LEARNED_FILE, "w", encoding="utf-8") as f:
        json.dump(learned, f, indent=2, ensure_ascii=False)


def category_names():
    names = list(load_db().keys())
    if DEFAULT_CATEGORY not in names:
        names.append(DEFAULT_CATEGORY)
    return names


def _shop_matches(shop, keyword):
    kw = _squash(keyword)
    if len(kw) < 4:
        return False
    if kw in _squash(shop):
        return True
    # Allow small OCR mistakes in a word of the shop name
    for word in re.findall(r"[a-z]+", shop.lower()):
        if len(word) >= 5 and SequenceMatcher(None, word, kw).ratio() >= 0.85:
            return True
    return False


def classify_by_shop(shop, db):
    if not shop:
        return None
    learned = load_learned()
    key = _squash(shop)
    if key in learned:
        return learned[key]
    for category, info in db.items():
        for keyword in info.get("shops", []):
            if _shop_matches(shop, keyword):
                return category
    return None


def classify_by_items(text, db):
    lowered = text.lower()
    best_category, best_hits = None, 0
    for category, info in db.items():
        hits = 0
        for keyword in info.get("items", []):
            pattern = r"\b" + re.escape(keyword.lower()) + r"s?\b"
            hits += len(re.findall(pattern, lowered))
        if hits > best_hits:
            best_category, best_hits = category, hits
    if best_hits >= MIN_ITEM_HITS:
        return best_category
    return None


def classify_bill(shop, text):
    # Returns (category, reason) so you can see why the app chose it
    db = load_db()
    category = classify_by_shop(shop, db)
    if category:
        return category, "shop name"
    category = classify_by_items(text, db)
    if category:
        return category, "items on the bill"
    return DEFAULT_CATEGORY, "no match"