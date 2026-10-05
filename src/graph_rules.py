"""Conservative entity normalization and explicit mass rules for the frozen lab corpus."""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from decimal import Decimal
from typing import Callable

SUBSTANCES = ["Heroine", "Cocaine", "Methamphetamine", "Amphetamine", "MDMA", "XLR-11",
              "Ketamine", "cần sa", "thuốc phiện", "côca"]
SUBSTANCE_SYNONYMS = {
    "thuốc lắc": "MDMA", "ecstasy": "MDMA", "ma túy đá": "Methamphetamine",
    "hàng đá": "Methamphetamine", "ke": "Ketamine", "khay": "Ketamine",
    "bạch phiến": "Heroine", "hêrôin": "Heroine", "heroin": "Heroine",
    "bồ đà": "cần sa",
}


def clean_name(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip().strip("\"'“”‘’").lower()
    return re.sub(r"\s+", " ", value).replace("tuý", "túy")


def normalize_crime(name: str) -> str:
    return clean_name(name).removeprefix("tội ").strip()


def link_entity(name: str, known: list[str], normalize: Callable[[str], str] = normalize_crime) -> str | None:
    if not name or not known:
        return None
    mention = normalize(name)
    candidates = {normalize(k): k for k in known if normalize(k)}
    if not mention:
        return None
    if mention in candidates:
        return candidates[mention]
    if normalize is normalize_crime:
        # Expand only an explicit shorthand, preserving the action verb.
        shorthand = re.fullmatch(r"(.+?) (?:chất )?ma túy", mention)
        if shorthand:
            expanded = shorthand.group(1) + " trái phép chất ma túy"
            if expanded in candidates:
                return candidates[expanded]
        action = mention.split(" trái phép", 1)[0]
        candidates = {k: v for k, v in candidates.items() if k.split(" trái phép", 1)[0] == action}
    matches = difflib.get_close_matches(mention, list(candidates), n=2, cutoff=0.9)
    if not matches:
        return None
    if len(matches) > 1:
        scores = [difflib.SequenceMatcher(None, mention, m).ratio() for m in matches]
        if scores[0] - scores[1] < 0.05:
            return None
    return candidates[matches[0]]


def canonical_substance(name: str) -> str:
    """Map an entire name; never collapse a mixture or a generic drug class."""
    if not name:
        return ''
    cleaned = clean_name(name)
    exact = {clean_name(s): s for s in SUBSTANCES}
    return SUBSTANCE_SYNONYMS.get(cleaned, exact.get(cleaned, name.strip()))


def find_substances(text: str) -> list[str]:
    lowered = clean_name(text)
    aliases = {**{clean_name(s): s for s in SUBSTANCES}, **SUBSTANCE_SYNONYMS}
    found = {canon for alias, canon in aliases.items()
             if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lowered)}
    return [s for s in SUBSTANCES if s in found]


UNIT = r"(?:kilôgam|kilogam|kg|gam|g)"
NUMBER = r"\d+(?:[.,]\d+)?"
MASS = re.compile(rf"(?<![\w.,])(?P<n>{NUMBER})\s*(?P<u>{UNIT})(?!\w)", re.I)


def grams(number: str, unit: str) -> float:
    factor = 1000 if clean_name(unit) in {"kg", "kilôgam", "kilogam"} else 1
    return float(Decimal(number.replace(",", ".")) * factor)


def parse_amount(amount: str) -> dict:
    """Accept a single mass observation, retaining uncertainty and original wording."""
    matches = list(MASS.finditer(amount))
    if len(matches) != 1 or re.search(r"\d\s*[-–]\s*\d|\btừ\b|\bđến\b", amount, re.I):
        return {"grams": None, "qualifier": "unknown"}
    m = matches[0]
    prefix = clean_name(amount[:m.start()])
    qualifier = "gt" if re.search(r"\bhơn\b", prefix) else "eq"
    if re.search(r"\bgần\b|\bkhoảng\b|\bxấp xỉ\b|\bdưới\b", prefix):
        qualifier = "approx"
    return {"grams": grams(m['n'], m['u']), "qualifier": qualifier}


def mass_thresholds(text: str) -> list[dict]:
    """Parse named substances in an explicit point with lower-inclusive/upper-exclusive mass."""
    rules = []
    for point in re.split(r"\n\s*[a-zđ]\)\s*", text):
        if "có khối lượng" not in point:
            continue
        names, condition = point.split("có khối lượng", 1)
        # Plant parts/resins need their own categories; don't treat them as pure substances.
        if re.search(r"nhựa|lá|rễ|thân|cành|hoa|quả|cao côca", names, re.I):
            continue
        substances = [s for s in SUBSTANCES if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", names, re.I)]
        bound = re.search(rf"từ\s+({NUMBER})\s*({UNIT})\s+đến dưới\s+({NUMBER})\s*({UNIT})", condition, re.I)
        floor = re.search(rf"({NUMBER})\s*({UNIT})\s+trở lên", condition, re.I)
        if bound:
            lower, upper = grams(bound[1], bound[2]), grams(bound[3], bound[4])
        elif floor:
            lower, upper = grams(floor[1], floor[2]), None
        else:
            continue
        for s in substances:
            rules.append({"substance": s, "min_g": lower, "max_g": upper,
                          "evidence": names.strip() + " có khối lượng" + condition.split(";", 1)[0]})
    return rules


def matching_threshold(clause: dict, observation: dict) -> dict | None:
    amount = parse_amount(observation.get("amount", ""))
    if amount["grams"] is None or amount["qualifier"] not in {"eq", "gt"}:
        return None
    for rule in json.loads(clause.get("thresholds_json") or "[]"):
        if rule["substance"] != observation["name"] or amount["grams"] < rule["min_g"]:
            continue
        upper = rule["max_g"]
        if amount["qualifier"] == "gt" and upper is not None:
            continue  # A lower bound cannot prove an upper bound.
        if upper is None or amount["grams"] < upper:
            return rule
    return None


def bounded_facts(facts: list[str], max_facts: int, max_chars: int) -> list[str]:
    result, seen, size = [], set(), 0
    for fact in facts:
        if not fact or fact in seen:
            continue
        seen.add(fact)
        if len(result) >= max_facts:
            break
        if size + len(fact) > max_chars:
            continue  # Never cut a legal condition mid-sentence.
        result.append(fact)
        size += len(fact)
    return result
