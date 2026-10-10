"""Product -> PriceCatcher item mapping, with a human approval checkpoint.

`build_mapping` proposes a mapping from lookup_item using the item_group /
item_category / name. Each row is one of:
  include = "yes"    unambiguous, safe to use
  include = "no"     clearly a different product or variety
  include = "review" ambiguous; a human decides (`suggested_include` is only a hint)

Nothing is final until `approve_mapping` turns the review file into
item_mapping.csv, which refuses to run while any "review" row is unresolved
(unless the caller explicitly accepts the suggestions).
"""

from __future__ import annotations

import pandas as pd

PRODUCT_IDS = ("rice", "egg", "cooking_oil", "chicken")

REVIEW_COLUMNS = [
    "item_code",
    "item",
    "unit",
    "item_group",
    "item_category",
    "proposed_product",
    "include",
    "review_note",
    "variant",
    "suggested_include",
]
APPROVED_COLUMNS = REVIEW_COLUMNS + ["approval"]
VALID_INCLUDE = {"yes", "no", "review"}


class MappingNotApproved(RuntimeError):
    """Raised when unresolved 'review' rows remain."""


def _decision(product: str, include: str, note: str, variant: str, suggested: str | None = None):
    return product, include, note, variant, suggested or include


def propose(item: str, unit: str, category: str) -> tuple[str, str, str, str, str] | None:
    """Return (proposed_product, include, note, variant, suggested_include) or None
    when the item is not a candidate for any tracked product."""
    name = str(item).upper()
    category = str(category).upper()
    unit = str(unit).strip()

    if category == "BERAS":
        if "PULUT" in name:
            return _decision("rice", "no", "Glutinous rice (pulut), 1kg pack: different variety, not comparable to white rice.", "glutinous")
        if "BASMATHI" in name or "BASMATI" in name:
            return _decision("rice", "no", "Basmati: different variety and pack size.", "basmati")
        ten_kg = unit.replace(" ", "").lower() == "10kg"
        if "IMPORT" in name and ten_kg:
            return _decision("rice", "yes", "Imported white rice, 10kg bag. Brand items are normalised separately before averaging.", "white_import_10kg")
        return _decision(
            "rice",
            "review",
            "White rice; the lookup does not say whether it is local or imported (SST5% / Sabah brands) or confirm the grade. "
            "Mixing origins and grades needs a human decision.",
            "white_unspecified",
            "yes",
        )

    if category == "TELUR":
        if name.startswith("TELUR AYAM GRED"):
            grade = name.split("GRED", 1)[1].strip().split()[0]
            return _decision(
                "egg",
                "yes",
                f"Hen egg grade {grade}, pack {unit}. Grades and pack sizes stay separate items and are normalised per item before averaging.",
                f"hen_grade_{grade}_{unit.replace(' ', '')}",
            )
        if "KAMPUNG" in name:
            return _decision("egg", "review", "Free-range (kampung) hen egg: different product and price level; suggest excluding.", "hen_kampung", "no")
        if any(k in name for k in ("PUYUH", "ITIK", "MASIN")):
            return _decision("egg", "no", "Not a hen egg (quail, duck or salted).", "other_egg")
        return None

    if category == "AYAM":
        if "BELANDA" in name:
            return _decision("chicken", "no", "Turkey (ayam belanda), not chicken.", "turkey")
        if "TUA HIDUP" in name:
            return _decision("chicken", "review", "Old hen sold live: different basis (live weight) and bird type; suggest excluding.", "live_old_hen", "no")
        if "HIDUP" in name:
            return _decision("chicken", "review", "Live chicken priced per kg live weight, a different basis from dressed chicken; suggest excluding.", "live", "no")
        if "BERSIH" in name:
            return _decision("chicken", "yes", "Whole dressed chicken, per kg.", "whole_dressed")
        if any(k in name for k in ("DADA", "KEPAK", "PAHA", "THIGH", "WHOLE LEG")):
            return _decision("chicken", "no", "Chicken part, not whole chicken (brief: do not mix parts with whole chicken).", "part")
        return None

    if category == "MINYAK DAN LEMAK":
        if name.startswith("MINYAK MASAK PAKET"):
            return _decision(
                "cooking_oil",
                "review",
                "1kg 'paket' oil, assumed to be the government-subsidised packet (inferred from the name; the lookup does not say). "
                "Subsidised and unsubsidised oil must not be mixed without approval; suggest excluding from the main index.",
                "subsidised_packet_1kg",
                "no",
            )
        if name.startswith("MINYAK MASAK SEBATIAN"):
            return _decision("cooking_oil", "yes", "Blended (sebatian) branded cooking oil. Kept as its own item, normalised before averaging.", "branded_blended")
        if name.startswith("MINYAK MASAK TULEN"):
            return _decision("cooking_oil", "yes", "Pure palm (tulen) branded cooking oil. Kept as its own item, normalised before averaging.", "branded_pure_palm")
        if name.startswith("MINYAK JAGUNG"):
            return _decision("cooking_oil", "no", "Corn oil: a different oil type and price level.", "corn_oil")
        return None  # ghee etc. are not cooking oil

    return None


def build_mapping(lookup: pd.DataFrame) -> pd.DataFrame:
    """Candidate mapping for every lookup item that matches a tracked product."""
    needed = {"item_code", "item", "unit", "item_group", "item_category"}
    missing = needed - set(lookup.columns)
    if missing:
        raise ValueError(f"lookup_item is missing columns {sorted(missing)}; found {list(lookup.columns)}")
    rows = []
    for rec in lookup.itertuples(index=False):
        decision = propose(rec.item, rec.unit, rec.item_category)
        if decision is None:
            continue
        product, include, note, variant, suggested = decision
        rows.append(
            {
                "item_code": int(rec.item_code),
                "item": rec.item,
                "unit": rec.unit,
                "item_group": rec.item_group,
                "item_category": rec.item_category,
                "proposed_product": product,
                "include": include,
                "review_note": note,
                "variant": variant,
                "suggested_include": suggested,
            }
        )
    out = pd.DataFrame(rows, columns=REVIEW_COLUMNS)
    return out.sort_values(["proposed_product", "include", "item_code"], ignore_index=True)


def candidate_item_codes(review: pd.DataFrame) -> list[int]:
    """Every item worth retaining from the monthly files (all proposed rows)."""
    return sorted(int(c) for c in review.loc[review["proposed_product"].astype(str) != "", "item_code"])


def approve_mapping(review: pd.DataFrame, accept_suggestions: bool = False) -> pd.DataFrame:
    """Turn a (human-edited) review file into the final mapping."""
    df = review.copy()
    missing = set(REVIEW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Review file is missing columns {sorted(missing)}")
    df["include"] = df["include"].astype(str).str.strip().str.lower()
    df["suggested_include"] = df["suggested_include"].astype(str).str.strip().str.lower()
    bad = df[~df["include"].isin(VALID_INCLUDE)]
    if len(bad):
        raise ValueError(f"include must be yes/no/review; bad rows: {bad['item_code'].tolist()}")
    pending = df[df["include"] == "review"]
    df["approval"] = "reviewed"
    if len(pending):
        if not accept_suggestions:
            items = "; ".join(f"{r.item_code} {r.item}" for r in pending.itertuples())
            raise MappingNotApproved(
                f"{len(pending)} item(s) still marked 'review'. Edit the 'include' column to yes/no, "
                f"or re-run with --accept-suggestions to take the suggested values. Pending: {items}"
            )
        if not pending["suggested_include"].isin({"yes", "no"}).all():
            raise ValueError("suggested_include must be yes or no for every review row")
        idx = pending.index
        df.loc[idx, "include"] = df.loc[idx, "suggested_include"]
        df.loc[idx, "approval"] = "suggestion_accepted"
    df["include"] = df["include"].map({"yes": "yes", "no": "no"})
    return df[APPROVED_COLUMNS].sort_values(["proposed_product", "item_code"], ignore_index=True)


def included_items(approved: pd.DataFrame) -> pd.DataFrame:
    """Approved items that feed the four product indexes."""
    sel = approved[(approved["include"] == "yes") & approved["proposed_product"].isin(PRODUCT_IDS)]
    return sel[["item_code", "proposed_product"]].rename(columns={"proposed_product": "product"}).reset_index(drop=True)
