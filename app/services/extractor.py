from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Seed lexicons (short MVP subset from your memo; expand over time)
LEXICONS = {
    "textual_analysis": [
        "seeking admission", "applicants for admission", "ordinary meaning",
        "dictionary", "superfluous", "redundant", "canon against superfluous"
    ],
    "structure_context": [
        "statutory scheme", "arriving alien", "once inside the united states",
        "1226(c)", "laken riley act", "jennings"
    ],
    "historical_practice": [
        "historical practice", "longstanding practice", "consistent practice", "past practice"
    ],
    "statutory_history": [
        "iirira", "45,000", "detention capacity", "deferred implementation", "h.r. rep."
    ],
    "statutory_purpose": [
        "purpose", "absurd", "equal footing", "deter", "deterrent", "congress's purpose"
    ],
    "precedent": [
        "jennings v. rodriguez", "jennings", "buenrostro", "chen", "calzado", "hurtado"
    ],
}


@dataclass
class ExtractedCase:
    petitioner_facts: dict[str, Any]
    petition_facts: dict[str, Any]
    respondent_position: dict[str, Any]
    reasoning_basis: dict[str, Any]
    precedent_citations: dict[str, Any]
    holdings: dict[str, Any]
    evidence_spans: dict[str, Any]
    flags: dict[str, Any]
    confidence: float


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _find_hits(text: str, phrases: list[str]) -> list[str]:
    t = _normalize(text)
    hits = []
    for p in phrases:
        if p.lower() in t:
            hits.append(p)
    return hits


def _extract_holdings(text: str) -> tuple[dict, dict]:
    t = _normalize(text)
    evidence = {}

    provision = None
    subprovision = None
    if "1226(a)" in t:
        provision = "1226"
        subprovision = "1226(a)"
    elif "1225(b)(2)(a)" in t:
        provision = "1225"
        subprovision = "1225(b)(2)(A)"
    elif "§ 1226" in text or " 1226 " in t:
        provision = "1226"
    elif "§ 1225" in text or " 1225 " in t:
        provision = "1225"

    bond = None
    if "bond hearing" in t:
        if any(x in t for x in ["eligible for a bond hearing", "entitled to a bond hearing", "must receive a bond hearing"]):
            bond = "eligible"
        elif any(x in t for x in ["not eligible for a bond hearing", "no bond hearing", "mandatory detention"]):
            bond = "mandatory_detention_or_no_bond"

    habeas_relief = None
    if "granted in part and denied in part" in t:
        habeas_relief = "granted_in_part_and_denied_in_part"
    elif "granted in part" in t:
        habeas_relief = "granted_in_part"
    elif "denied in part" in t:
        habeas_relief = "denied_in_part"
    elif re.search(r"\bpetition\b.*\bgranted\b", t) or re.search(r"\bhabeas\b.*\bgranted\b", t):
        habeas_relief = "granted"
    elif re.search(r"\bpetition\b.*\bdenied\b", t) or re.search(r"\bhabeas\b.*\bdenied\b", t):
        habeas_relief = "denied"

    # Extract rough evidence snippets
    for key in ["1225", "1226", "bond hearing", "mandatory detention", "granted", "denied"]:
        idx = t.find(key)
        if idx != -1:
            start = max(0, idx - 120)
            end = min(len(text), idx + 160)
            evidence[key] = text[start:end]

    return {
        "applicable_provision": provision,
        "applicable_subprovision": subprovision,
        "bond_status": bond,  # eligible / mandatory_detention_or_no_bond / null
        "habeas_relief": habeas_relief,
    }, evidence


def _extract_detention_location_flags(text: str) -> tuple[dict, dict]:
    t = _normalize(text)
    border_markers = [
        "at the border", "near the border", "southern border", "arriving alien",
        "port of entry", "arriving in the united states"
    ]
    interior_markers = [
        "within the country", "once inside the united states", "interior", "already here"
    ]

    border_hits = [m for m in border_markers if m in t]
    interior_hits = [m for m in interior_markers if m in t]

    is_border = len(border_hits) > 0 and len(interior_hits) == 0
    is_interior = len(interior_hits) > 0

    return {
        "is_border_or_near_border_detention": is_border if (border_hits or interior_hits) else None,
        "is_interior_detention_focus": is_interior if (border_hits or interior_hits) else None,
    }, {"border_hits": border_hits, "interior_hits": interior_hits}


def extract_case(text: str) -> ExtractedCase:
    t = text or ""

    reasoning_basis = {}
    precedent_citations = {}
    evidence_spans = {"reasoning_basis": {}, "holdings": {}, "location_flags": {}}

    total_hits = 0
    for category, phrases in LEXICONS.items():
        hits = _find_hits(t, phrases)
        score = len(hits)
        total_hits += score

        if category == "precedent":
            precedent_citations = {"hits": hits, "count": score}
        else:
            reasoning_basis[category] = {
                "present": score > 0,
                "score": score,
                "hits": hits,
            }
            if hits:
                evidence_spans["reasoning_basis"][category] = hits[:10]

    holdings, holdings_evidence = _extract_holdings(t)
    evidence_spans["holdings"] = holdings_evidence

    flags, loc_evidence = _extract_detention_location_flags(t)
    evidence_spans["location_flags"] = loc_evidence

    # Minimal respondent/petitioner extraction stubs (expand later with LLM or better rules)
    respondent_position = {
        "claimed_detention_provision": "1225" if "detained pursuant to § 1225" in _normalize(t) else (
            "1226" if "detained pursuant to § 1226" in _normalize(t) else None
        )
    }

    petitioner_facts = {
        "asylum_mentions": bool(re.search(r"\basylum\b", t, re.IGNORECASE)),
        "sijs_mentions": bool(re.search(r"\bSIJ(S)?\b", t, re.IGNORECASE)),
        "cat_mentions": bool(re.search(r"\bCAT\b|Convention Against Torture", t, re.IGNORECASE)),
        "entered_without_inspection_mentions": bool(re.search(r"without inspection|entered without inspection", t, re.IGNORECASE)),
    }

    petition_facts = {
        "habeas_mentions": bool(re.search(r"\bhabeas\b", t, re.IGNORECASE)),
        "bond_hearing_mentions": bool(re.search(r"bond hearing", t, re.IGNORECASE)),
    }

    confidence = min(0.95, 0.2 + (total_hits * 0.03))

    return ExtractedCase(
        petitioner_facts=petitioner_facts,
        petition_facts=petition_facts,
        respondent_position=respondent_position,
        reasoning_basis=reasoning_basis,
        precedent_citations=precedent_citations,
        holdings=holdings,
        evidence_spans=evidence_spans,
        flags=flags,
        confidence=confidence,
    )