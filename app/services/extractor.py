from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Seed lexicons (short MVP subset from memo; expand over time)
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

PHRASE_SIGNAL_LIBRARY = [
    {
        "phrase_key": "ordinary_meaning_textualism",
        "phrase_label": "ordinary meaning / textual analysis",
        "phrase_category": "textualism",
        "aliases": [
            "ordinary meaning",
            "dictionary",
            "dictionary analysis",
            "textual analysis",
            "plain meaning",
        ],
    },
    {
        "phrase_key": "statutory_scheme_structure",
        "phrase_label": "statutory scheme / structure",
        "phrase_category": "structure_context",
        "aliases": [
            "statutory scheme",
            "superfluous",
            "redundant",
            "canon against superfluous",
        ],
    },
    {
        "phrase_key": "historical_practice",
        "phrase_label": "historical practice",
        "phrase_category": "historical_practice",
        "aliases": [
            "historical practice",
            "longstanding practice",
            "consistent practice",
            "past practice",
        ],
    },
    {
        "phrase_key": "due_process_bond_hearing",
        "phrase_label": "due process / bond hearing",
        "phrase_category": "bond_hearing_relief",
        "aliases": [
            "prolonged detention",
            "due process",
            "eligible for a bond hearing",
            "entitled for a bond hearing",
            "entitled to a bond hearing",
            "must receive a bond hearing",
            "shall receive a bond hearing",
            "bond hearing is required",
        ],
    },
    {
        "phrase_key": "interior_presence",
        "phrase_label": "already inside the United States",
        "phrase_category": "interior_detention",
        "aliases": [
            "once inside the united states",
            "within the country",
            "already within the country",
            "interior",
            "already here",
        ],
    },
    {
        "phrase_key": "arriving_alien_border",
        "phrase_label": "arriving alien / border entry",
        "phrase_category": "border_detention",
        "aliases": [
            "arriving alien",
            "applicants for admission",
            "port of entry",
            "at the border",
            "near the border",
            "southern border",
            "arriving in the united states",
        ],
    },
    {
        "phrase_key": "mandatory_detention_no_bond",
        "phrase_label": "mandatory detention / no bond",
        "phrase_category": "mandatory_detention",
        "aliases": [
            "mandatory detention",
            "no bond hearing",
            "not eligible for a bond hearing",
            "ineligible for a bond hearing",
        ],
    },
    {
        "phrase_key": "deterrence_statutory_purpose",
        "phrase_label": "deterrence / statutory purpose",
        "phrase_category": "statutory_purpose",
        "aliases": [
            "statutory purpose",
            "purpose",
            "deter",
            "deterrent",
            "congress's purpose",
        ],
    },
]


@dataclass
class ExtractedCase:
    petitioner_facts: dict[str, Any]
    petition_facts: dict[str, Any]
    respondent_position: dict[str, Any]
    reasoning_basis: dict[str, Any]
    precedent_citations: dict[str, Any]
    holdings: dict[str, Any]
    phrase_signals: list[dict[str, Any]]
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

def _window(text: str, start: int, end: int, radius: int = 180) -> str:
    s = max(0, start - radius)
    e = min(len(text), end + radius)
    return text[s:e]


def _first_match(text: str, patterns: list[str], flags=re.IGNORECASE | re.DOTALL):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None

def _find_alias_match(text: str, aliases: list[str]):
    for alias in aliases:
        m = re.search(re.escape(alias), text, re.IGNORECASE)
        if m:
            return alias, m
    return None, None


def _extract_phrase_signals(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    for entry in PHRASE_SIGNAL_LIBRARY:
        matched_alias, match = _find_alias_match(text, entry["aliases"])
        if not match:
            continue

        evidence = _window(text, match.start(), match.end())
        signals.append(
            {
                "phrase_key": entry["phrase_key"],
                "phrase_label": entry["phrase_label"],
                "phrase_category": entry["phrase_category"],
                "matched_alias": matched_alias,
                "evidence": evidence,
            }
        )
        evidence_rows.append(
            {
                "phrase_key": entry["phrase_key"],
                "matched_alias": matched_alias,
                "evidence": evidence,
            }
        )

    return signals, evidence_rows


def _extract_holdings(text: str) -> tuple[dict, dict]:
    t = _normalize(text)
    evidence = {}

    # ---------------------------
    # Applicable detention provision
    # ---------------------------
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

    # ---------------------------
    # Bond hearing status
    # ---------------------------
    bond = None
    bond_positive_patterns = [
        r"(eligible|entitled)\s+for\s+a\s+bond\s+hearing",
        r"must\s+receive\s+a\s+bond\s+hearing",
        r"shall\s+receive\s+a\s+bond\s+hearing",
        r"bond\s+hearing\s+is\s+required",
    ]
    bond_negative_patterns = [
        r"(not\s+eligible|ineligible)\s+for\s+a\s+bond\s+hearing",
        r"no\s+bond\s+hearing",
        r"mandatory\s+detention",
    ]

    m_bond_pos = _first_match(text, bond_positive_patterns)
    m_bond_neg = _first_match(text, bond_negative_patterns)

    if m_bond_pos:
        bond = "eligible"
        evidence["bond_status_signal"] = _window(text, m_bond_pos.start(), m_bond_pos.end())
    elif m_bond_neg:
        bond = "mandatory_detention_or_no_bond"
        evidence["bond_status_signal"] = _window(text, m_bond_neg.start(), m_bond_neg.end())

    # ---------------------------
    # Habeas disposition (grant / deny / partial / unknown)
    # ---------------------------
    habeas_relief = None
    non_merits_disposition = None

    # Partial first (most specific)
    partial_patterns = [
        r"(habeas\s+petition|petition\s+for\s+writ\s+of\s+habeas\s+corpus|petition|writ)[^.]{0,140}\bgranted\s+in\s+part\s+and\s+denied\s+in\s+part\b",
        r"(habeas\s+petition|petition\s+for\s+writ\s+of\s+habeas\s+corpus|petition|writ)[^.]{0,140}\bdenied\s+in\s+part\s+and\s+granted\s+in\s+part\b",
        r"\bgranted\s+in\s+part\s+and\s+denied\s+in\s+part\b",
        r"\bdenied\s+in\s+part\s+and\s+granted\s+in\s+part\b",
        r"(habeas\s+petition|petition|writ)[^.]{0,140}\bgranted\s+in\s+part\b",
        r"(habeas\s+petition|petition|writ)[^.]{0,140}\bdenied\s+in\s+part\b",
    ]

    # Explicit habeas / petition / writ grant/deny
    grant_patterns = [
        r"\bhabeas\s+petition\b[^.]{0,160}\b(is\s+)?granted\b",
        r"\bpetition\s+for\s+writ\s+of\s+habeas\s+corpus\b[^.]{0,160}\b(is\s+)?granted\b",
        r"\bwrit\b[^.]{0,120}\b(is\s+)?granted\b",
        r"\bhabeas\s+relief\b[^.]{0,120}\b(is\s+)?granted\b",
        r"\bthe\s+court\s+grants\s+the\s+(habeas\s+)?petition\b",
        r"\bpetition\b[^.]{0,140}\bgranted\b",
    ]
    deny_patterns = [
        r"\bhabeas\s+petition\b[^.]{0,160}\b(is\s+)?denied\b",
        r"\bpetition\s+for\s+writ\s+of\s+habeas\s+corpus\b[^.]{0,160}\b(is\s+)?denied\b",
        r"\bwrit\b[^.]{0,120}\b(is\s+)?denied\b",
        r"\bhabeas\s+relief\b[^.]{0,120}\b(is\s+)?denied\b",
        r"\bthe\s+court\s+denies\s+the\s+(habeas\s+)?petition\b",
        r"\bpetition\b[^.]{0,140}\bdenied\b",
    ]

    # Non-merits dispositions (for now keep habeas_relief unknown)
    moot_patterns = [
        r"\b(habeas\s+petition|petition|writ)\b[^.]{0,160}\bdismissed\s+as\s+moot\b",
        r"\bdismissed\s+as\s+moot\b",
    ]
    dismissed_patterns = [
        r"\b(habeas\s+petition|petition|writ)\b[^.]{0,160}\bdismissed\b",
    ]

    # False-positive phrases to avoid treating as habeas grant/deny
    false_positive_motion_patterns = [
        r"\bmotion\s+to\s+dismiss\b[^.]{0,120}\bgranted\b",
        r"\brespondent'?s\s+motion\b[^.]{0,120}\bgranted\b",
        r"\bmotion\s+for\s+summary\s+judgment\b[^.]{0,120}\bgranted\b",
    ]

    m_partial = _first_match(text, partial_patterns)
    m_grant = _first_match(text, grant_patterns)
    m_deny = _first_match(text, deny_patterns)
    m_moot = _first_match(text, moot_patterns)
    m_dismissed = _first_match(text, dismissed_patterns)
    m_false_motion = _first_match(text, false_positive_motion_patterns)

    if m_partial:
        # Preserve your existing schema values where possible
        raw_span = m_partial.group(0).lower()
        if "granted in part" in raw_span and "denied in part" in raw_span:
            habeas_relief = "granted_in_part_and_denied_in_part"
        elif "granted in part" in raw_span:
            habeas_relief = "granted_in_part"
        elif "denied in part" in raw_span:
            habeas_relief = "denied_in_part"
        evidence["habeas_relief_signal"] = _window(text, m_partial.start(), m_partial.end())
    else:
        # Only trust generic grant if it's not just a motion grant
        if m_grant:
            span = _window(text, m_grant.start(), m_grant.end())
            if not (m_false_motion and m_false_motion.start() >= max(0, m_grant.start() - 80) and m_false_motion.start() <= m_grant.end() + 80):
                habeas_relief = "granted"
                evidence["habeas_relief_signal"] = span

        if habeas_relief is None and m_deny:
            habeas_relief = "denied"
            evidence["habeas_relief_signal"] = _window(text, m_deny.start(), m_deny.end())

    # Non-merits signals (used only when no merits disposition found)
    if habeas_relief is None:
        if m_moot:
            non_merits_disposition = "dismissed_as_moot"
            evidence["non_merits_signal"] = _window(text, m_moot.start(), m_moot.end())
        elif m_dismissed:
            non_merits_disposition = "dismissed"
            evidence["non_merits_signal"] = _window(text, m_dismissed.start(), m_dismissed.end())

    # Generic evidence snippets for key signals (helps UI)
    for key in ["1225", "1226", "bond hearing", "mandatory detention", "granted", "denied"]:
        idx = t.find(key)
        if idx != -1 and key not in evidence:
            evidence[key] = text[max(0, idx - 120): min(len(text), idx + 160)]

    holdings = {
        "applicable_provision": provision,
        "applicable_subprovision": subprovision,
        "bond_status": bond,
        "habeas_relief": habeas_relief,  # granted / denied / partial variants / null
    }

    # Optional extra field for UI/QA (won't break anything)
    if non_merits_disposition:
        holdings["non_merits_disposition"] = non_merits_disposition

    return holdings, evidence


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
    evidence_spans = {
        "reasoning_basis": {},
        "holdings": {},
        "location_flags": {},
        "phrase_signals": [],
    }

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

    phrase_signals, phrase_evidence = _extract_phrase_signals(t)
    evidence_spans["phrase_signals"] = phrase_evidence
    total_hits += len(phrase_signals)

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
        phrase_signals=phrase_signals,
        evidence_spans=evidence_spans,
        flags=flags,
        confidence=confidence,
    )