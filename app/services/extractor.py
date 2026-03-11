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

PRO_SE_PATTERNS = [
    r"\bpro se\b",
    r"\bappearing pro se\b",
    r"\bfiled pro se\b",
    r"\bself-represented\b",
    r"\bwithout counsel\b",
]

REPRESENTED_PATTERNS = [
    r"\bthrough counsel\b",
    r"\brepresented by counsel\b",
    r"\bpetitioner, through counsel\b",
    r"\bcounsel for petitioner\b",
    r"\battorney for petitioner\b",
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
    representation_status: str | None
    representation_evidence: str | None
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

def _all_matches(text: str, patterns: list[str], flags=re.IGNORECASE | re.DOTALL):
    matches = []
    for p in patterns:
        matches.extend(list(re.finditer(p, text, flags)))
    return matches


def _count_matches(text: str, patterns: list[str], flags=re.IGNORECASE | re.DOTALL) -> int:
    return len(_all_matches(text, patterns, flags))


def _priority_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    chunks: list[str] = []
    chunks.append(text[:5000])

    anchor_patterns = [
        r"\bIT IS ORDERED\b",
        r"\bIT IS FURTHER ORDERED\b",
        r"\bThe Court concludes\b",
        r"\bThe Court holds\b",
        r"\bThe Court finds\b",
        r"\bSummary\b",
        r"\bConclusion\b",
        r"\bAccordingly\b",
        r"\bThe petition is\b",
        r"\bThe habeas petition is\b",
        r"\bpetition for writ of habeas corpus\b",
        r"\bbond hearing class\b",
    ]

    for pattern in anchor_patterns:
        try:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                chunks.append(_window(text, m.start(), m.end(), radius=900))
        except re.error:
            continue

    return "\n\n".join(chunks)


def _weighted_pattern_score(priority_text: str, full_text: str, patterns: list[str]) -> int:
    """
    Give extra weight to matches in dispositive/summary sections.
    """
    return (2 * _count_matches(priority_text, patterns)) + _count_matches(full_text, patterns)

def _operative_language_score(text: str, patterns: list[str]) -> int:
    if not isinstance(text, str) or not text:
        return 0

    total = 0
    for p in patterns:
        wrapped_patterns = [
            rf"(the court (holds|concludes|finds)[^.]*{p})",
            rf"(it is ordered[^.]*{p})",
            rf"(petition[^.]*{p})",
            rf"(injunction[^.]*{p})",
        ]
        try:
            total += _count_matches(text, wrapped_patterns)
        except re.error:
            continue
    return total

def _has_negative_prefix(text: str, start: int) -> bool:
    prefix = text[max(0, start - 24):start].lower()
    return (
        "non-" in prefix
        or "non " in prefix
        or "not an " in prefix
        or "not a " in prefix
        or "no " in prefix
    )


def _first_match(text: str, patterns: list[str], flags=re.IGNORECASE | re.DOTALL):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None

def _find_alias_match(text: str, aliases: list[str]):
    for alias in aliases:
        for m in re.finditer(re.escape(alias), text, re.IGNORECASE):
            alias_l = alias.lower()

            if alias_l == "arriving alien" and _has_negative_prefix(text, m.start()):
                continue

            if alias_l == "at the border":
                snippet = text[max(0, m.start() - 120): min(len(text), m.end() + 120)].lower()
                if "not at the border" in snippet or "within the territorial boundaries" in snippet:
                    continue

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

def _first_regex_match(text: str, patterns: list[str]):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m
    return None

def _opening_and_closing_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return (text[:4000] or "") + "\n\n" + (text[-2500:] or "")


def _first_prefer_priority_match(priority_text: str, full_text: str, patterns: list[str]):
    m = _first_match(priority_text, patterns)
    if m:
        return m
    return _first_match(full_text, patterns)

def _span_text(text: str, match, radius: int = 220) -> str:
    if not match:
        return ""
    return _window(text, match.start(), match.end(), radius=radius)


def _looks_like_prior_or_appellate_context(span: str) -> bool:
    s = (span or "").lower()
    appellate_markers = [
        "district court had granted",
        "district court had denied",
        "previously granted",
        "previously denied",
        "the lower court",
        "on appeal",
        "we reverse",
        "we vacate",
        "we remand",
        "reversed the district court",
        "vacated the district court",
        "remanded to the district court",
        "judgment granting the habeas petition",
        "judgment denying the habeas petition",
    ]
    return any(marker in s for marker in appellate_markers)


def _looks_like_current_grant_context(span: str) -> bool:
    s = (span or "").lower()
    current_markers = [
        "i grant the petition",
        "the court will grant",
        "the court grants",
        "petition is granted",
        "grant the writ",
        "grant his petition",
        "grant her petition",
        "grant their petition",
        "grant the petition and order",
        "order the immigration court to hold a bond hearing",
        "order respondent to provide a bond hearing",
        "constitutionally entitled to a bond hearing",
        "entitled to a bond hearing",
        "injunctive relief",
        "it is ordered",
        "the court orders",
    ]
    return any(marker in s for marker in current_markers)


def _looks_like_current_deny_context(span: str) -> bool:
    s = (span or "").lower()
    current_markers = [
        "the court denies",
        "petition is denied",
        "habeas petition is denied",
        "petition for writ of habeas corpus is denied",
        "deny the petition",
    ]
    return any(marker in s for marker in current_markers)


def _looks_like_represented_case(text: str) -> tuple[bool, str | None]:
    scope = _opening_and_closing_text(text)

    represented_patterns = REPRESENTED_PATTERNS + [
        r"\bcounsel for petitioners?\b",
        r"\bcounsel for plaintiff[s]?\b",
        r"\bpetitioner[s]?, through counsel\b",
        r"\bthrough his counsel\b",
        r"\bthrough her counsel\b",
        r"\bthrough their counsel\b",
        r"\battorneys? for petitioners?\b",
        r"\bappeared through counsel\b",
        r"\bby and through counsel\b",
        r"\bplaintiffs?-appellees?\b",
        r"\bdefendants?-appellants?\b",
        r"\bamic[iu]s?\b",
        r"\battorney[s]?\s+for\s+petitioner[s]?\b",
        r"\battorney[s]?\s+for\s+plaintiff[s]?\b",
    ]

    m = _first_regex_match(scope, represented_patterns)
    if m:
        return True, _window(scope, m.start(), m.end())

    return False, None

def _extract_representation_status(text: str) -> tuple[str | None, str | None]:
    represented, represented_evidence = _looks_like_represented_case(text)
    if represented:
        return "represented", represented_evidence

    # Only trust pro se when it appears in the opening/closing portions,
    # not anywhere in the middle of a long opinion where it may be quoted background.
    scope = _opening_and_closing_text(text)
    pro_se_match = _first_regex_match(scope, PRO_SE_PATTERNS)
    if pro_se_match:
        return "pro_se", _window(scope, pro_se_match.start(), pro_se_match.end())

    return "unknown", None

def _extract_holdings(text: str) -> tuple[dict, dict]:
    t = _normalize(text)
    ptext = _priority_text(text)
    evidence = {}

    # ---------------------------
    # Applicable detention provision
    # ---------------------------
    provision = None
    subprovision = None

    explicit_1225_b1bii = [
        r"detained pursuant to §?\s*1225\(b\)\(1\)\(b\)\(ii\)",
        r"under §?\s*1225\(b\)\(1\)\(b\)\(ii\)",
        r"§?\s*235\(b\)\(1\)\(b\)\(ii\)",
    ]
    explicit_1225_b2a = [
        r"detained pursuant to §?\s*1225\(b\)\(2\)\(a\)",
        r"under §?\s*1225\(b\)\(2\)\(a\)",
        r"§?\s*1225\(b\)\(2\)\(a\)",
    ]
    explicit_1226a = [
        r"detained pursuant to §?\s*1226\(a\)",
        r"under §?\s*1226\(a\)",
        r"governed by §?\s*1226\(a\)",
        r"subject to detention under §?\s*1226\(a\)",
    ]
    explicit_1226c = [
        r"detained pursuant to §?\s*1226\(c\)",
        r"under §?\s*1226\(c\)",
        r"governed by §?\s*1226\(c\)",
        r"subject to detention under §?\s*1226\(c\)",
    ]

    if _count_matches(ptext, explicit_1225_b1bii):
        provision = "1225"
        subprovision = "1225(b)(1)(B)(ii)"
    elif _count_matches(ptext, explicit_1225_b2a):
        provision = "1225"
        subprovision = "1225(b)(2)(A)"
    elif _count_matches(ptext, explicit_1226a):
        provision = "1226"
        subprovision = "1226(a)"
    elif _count_matches(ptext, explicit_1226c):
        provision = "1226"
        subprovision = "1226(c)"
    else:
        patterns_1225 = [
            r"§\s*1225",
            r"\b1225\b",
            r"§\s*235",
            r"\b235\(b\)\(1\)\(b\)\(ii\)",
            r"\b235\(b\)\(2\)\(a\)",
            r"\bcredible fear\b",
            r"\bapplicants? for admission\b",
            r"\bseeking admission\b",
            r"\bparole\b",
            r"\barriving alien\b",
            r"\bentering without inspection\b",
        ]
        patterns_1226 = [
            r"§\s*1226",
            r"\b1226\b",
            r"\b1226\(a\)\b",
            r"\b1226\(c\)\b",
            r"\bcustody redetermination\b",
            r"\brevok[e|ing].{0,30}bond\b",
            r"\bbond under §?\s*1226\b",
            r"\bdetained pursuant to §?\s*1226\b",
        ]

        score_1225 = _weighted_pattern_score(ptext, text, patterns_1225)
        score_1226 = _weighted_pattern_score(ptext, text, patterns_1226)

        score_1225 += 3 * _operative_language_score(
            text,
            [
                r"1225",
                r"235\(b\)",
                r"1225\(b\)\(1\)\(b\)\(ii\)",
                r"1225\(b\)\(2\)\(a\)",
                r"credible fear",
            ],
        )
        score_1226 += 3 * _operative_language_score(
            text,
            [
                r"1226",
                r"1226\(a\)",
                r"1226\(c\)",
                r"bond hearing",
                r"custody redetermination",
            ],
        )

        if re.search(r"\bnon-arriving alien\b|\bwithin the territorial boundaries\b|\bonce inside the united states\b", text, re.IGNORECASE):
            score_1226 += 1
        if re.search(r"\bcredible fear\b|\bapplicants? for admission\b|\b235\(b\)\b", text, re.IGNORECASE):
            score_1225 += 1

        if score_1225 > score_1226:
            provision = "1225"
        elif score_1226 > score_1225:
            provision = "1226"
        elif "§ 1225" in text or " 1225 " in t:
            provision = "1225"
        elif "§ 1226" in text or " 1226 " in t:
            provision = "1226"

        if provision == "1225":
            if _count_matches(ptext, [r"§?\s*1225\(b\)\(1\)\(b\)\(ii\)", r"§?\s*235\(b\)\(1\)\(b\)\(ii\)"]) or _count_matches(text, [r"§?\s*1225\(b\)\(1\)\(b\)\(ii\)", r"§?\s*235\(b\)\(1\)\(b\)\(ii\)"]) >= 2:
                subprovision = "1225(b)(1)(B)(ii)"
            elif _count_matches(ptext, [r"§?\s*1225\(b\)\(2\)\(a\)"]) or _count_matches(text, [r"§?\s*1225\(b\)\(2\)\(a\)"]) >= 2:
                subprovision = "1225(b)(2)(A)"
        elif provision == "1226":
            # tighter than before: only assign subsection when it is explicit enough
            if _count_matches(ptext, [r"§?\s*1226\(a\)"]) >= 1 or _count_matches(text, explicit_1226a) >= 1 or _count_matches(text, [r"§?\s*1226\(a\)"]) >= 2:
                subprovision = "1226(a)"
            elif _count_matches(ptext, [r"§?\s*1226\(c\)"]) >= 1 or _count_matches(text, explicit_1226c) >= 1 or _count_matches(text, [r"§?\s*1226\(c\)"]) >= 2:
                subprovision = "1226(c)"

    # ---------------------------
    # Bond hearing status
    # ---------------------------
    bond = None
    bond_positive_patterns = [
        r"(eligible|entitled)\s+for\s+a\s+bond\s+hearing",
        r"entitled\s+to\s+a\s+bond\s+hearing",
        r"must\s+receive\s+a\s+bond\s+hearing",
        r"shall\s+receive\s+a\s+bond\s+hearing",
        r"bond\s+hearing\s+is\s+required",
        r"conduct\s+bond\s+hearings",
        r"constitutionally\s+entitled\s+to\s+a\s+bond\s+hearing",
        r"order(?:ed)?\s+.*bond hearing",
        r"grant(?:s|ed)?\s+.*bond hearing",
    ]
    bond_negative_patterns = [
        r"(not\s+eligible|ineligible)\s+for\s+a\s+bond\s+hearing",
        r"no\s+bond\s+hearing",
        r"subject\s+to\s+mandatory\s+detention",
        r"must\s+be\s+detained",
        r"mandatory\s+detention\s+without\s+bond",
    ]

    pos_score = _weighted_pattern_score(ptext, text, bond_positive_patterns)
    neg_score = _weighted_pattern_score(ptext, text, bond_negative_patterns)

    m_bond_pos = _first_prefer_priority_match(ptext, text, bond_positive_patterns)
    m_bond_neg = _first_prefer_priority_match(ptext, text, bond_negative_patterns)

    if pos_score > neg_score and m_bond_pos:
        bond = "eligible"
        evidence["bond_status_signal"] = _window(text, m_bond_pos.start(), m_bond_pos.end())
    elif neg_score > pos_score and m_bond_neg:
        bond = "mandatory_detention_or_no_bond"
        evidence["bond_status_signal"] = _window(text, m_bond_neg.start(), m_bond_neg.end())

    # ---------------------------
    # Habeas disposition
    # ---------------------------
    habeas_relief = None
    non_merits_disposition = None

    partial_patterns = [
        r"(habeas\s+petition|petition\s+for\s+writ\s+of\s+habeas\s+corpus|petition|writ)[^.]{0,160}\bgranted\s+in\s+part\s+and\s+denied\s+in\s+part\b",
        r"(habeas\s+petition|petition\s+for\s+writ\s+of\s+habeas\s+corpus|petition|writ)[^.]{0,160}\bdenied\s+in\s+part\s+and\s+granted\s+in\s+part\b",
        r"\bgranted\s+in\s+part\s+and\s+denied\s+in\s+part\b",
        r"\bdenied\s+in\s+part\s+and\s+granted\s+in\s+part\b",
    ]

    grant_patterns = [
        r"\bi grant (?:the|his|her|their)?\s*petition\b",
        r"\bthe court will grant (?:the|his|her|their)?\s*petition\b",
        r"\bthe court grants? (?:the|his|her|their)?\s*(?:habeas\s+)?petition\b",
        r"\bgrant(?:s|ed)?\s+the\s+petition\s+and\s+order(?:s|ed)?\b",
        r"\bgrant(?:s|ed)?\s+the\s+writ\b",
        r"\bhabeas\s+petition\b[^.]{0,180}\b(is\s+)?granted\b",
        r"\bpetition\s+for\s+writ\s+of\s+habeas\s+corpus\b[^.]{0,180}\b(is\s+)?granted\b",
        r"\bhabeas\s+relief\b[^.]{0,160}\b(is\s+)?granted\b",
        r"\bconstitutionally\s+entitled\s+to\s+a\s+bond\s+hearing\b",
        r"\bthe\s+court\s+affirms\s+its\s+previously-entered\s+injunctive\s+relief\b",
        r"\bthe\s+injunction\b[^.]{0,160}\b(is\s+)?modified\b",
        r"\border(?:s|ed)?\s+.*bond hearing\b",
    ]
    deny_patterns = [
        r"\bthe court denies? (?:the|his|her|their)?\s*(?:habeas\s+)?petition\b",
        r"\bhabeas\s+petition\b[^.]{0,180}\b(is\s+)?denied\b",
        r"\bpetition\s+for\s+writ\s+of\s+habeas\s+corpus\b[^.]{0,180}\b(is\s+)?denied\b",
        r"\bhabeas\s+relief\b[^.]{0,140}\b(is\s+)?denied\b",
        r"\bpetition\b[^.]{0,160}\bdenied\b",
        r"\breverse(?:d|s)?\s+the\s+district\s+court(?:'s)?\s+judgment\b[^.]{0,180}\bgrant(?:ed|ing)\s+the\s+habeas\s+petition\b",
        r"\bvacate(?:d|s)?\s+the\s+judgment\b[^.]{0,180}\bgrant(?:ed|ing)\s+the\s+habeas\s+petition\b",
    ]
    moot_patterns = [
        r"\b(habeas\s+petition|petition|writ)\b[^.]{0,180}\bdismissed\s+as\s+moot\b",
        r"\bdismissed\s+as\s+moot\b",
        r"\bclaims?\s+are\s+moot\b",
    ]
    dismissed_patterns = [
        r"\b(habeas\s+petition|petition|writ)\b[^.]{0,180}\bdismissed\b",
    ]
    false_positive_motion_patterns = [
        r"\bmotion\s+to\s+dismiss\b[^.]{0,140}\bgranted\b",
        r"\brespondent'?s\s+motion\b[^.]{0,140}\bgranted\b",
        r"\bmotion\s+for\s+summary\s+judgment\b[^.]{0,140}\bgranted\b",
        r"\bmotion\s+to\s+vacate\b[^.]{0,140}\bgranted\b",
    ]

    m_partial = _first_prefer_priority_match(ptext, text, partial_patterns)
    m_grant = _first_prefer_priority_match(ptext, text, grant_patterns)
    m_deny = _first_prefer_priority_match(ptext, text, deny_patterns)
    m_moot = _first_prefer_priority_match(ptext, text, moot_patterns)
    m_dismissed = _first_prefer_priority_match(ptext, text, dismissed_patterns)
    m_false_motion = _first_prefer_priority_match(ptext, text, false_positive_motion_patterns)

    if m_partial:
        raw_span = m_partial.group(0).lower()
        if "granted in part" in raw_span and "denied in part" in raw_span:
            habeas_relief = "granted_in_part_and_denied_in_part"
        evidence["habeas_relief_signal"] = _window(text, m_partial.start(), m_partial.end())
    else:
        grant_span = _span_text(text, m_grant)
        deny_span = _span_text(text, m_deny)

        grant_is_current = _looks_like_current_grant_context(grant_span)
        grant_is_prior_or_appellate = _looks_like_prior_or_appellate_context(grant_span)

        deny_is_current = _looks_like_current_deny_context(deny_span)
        deny_is_prior_or_appellate = _looks_like_prior_or_appellate_context(deny_span)

        if m_grant:
            if not (m_false_motion and abs(m_false_motion.start() - m_grant.start()) < 140):
                # Explicit current-case grant language should win even if the opinion also references prior proceedings.
                if grant_is_current:
                    habeas_relief = "granted"
                    evidence["habeas_relief_signal"] = grant_span
                # Only suppress generic grant language when it is clearly prior/appellate.
                elif not grant_is_prior_or_appellate and not m_deny:
                    habeas_relief = "granted"
                    evidence["habeas_relief_signal"] = grant_span

        if habeas_relief is None and m_deny:
            # Explicit current-case deny language wins.
            if deny_is_current:
                habeas_relief = "denied"
                evidence["habeas_relief_signal"] = deny_span
            # Appellate reversal/vacatur of granted relief should count as denied.
            elif re.search(r"\breverse(?:d|s)?\b|\bvacate(?:d|s)?\b", deny_span, re.IGNORECASE):
                habeas_relief = "denied"
                evidence["habeas_relief_signal"] = deny_span
            # Generic deny language only if it is not clearly prior/appellate.
            elif not deny_is_prior_or_appellate:
                habeas_relief = "denied"
                evidence["habeas_relief_signal"] = deny_span

    if habeas_relief is None:
        if m_moot:
            non_merits_disposition = "dismissed_as_moot"
            evidence["non_merits_signal"] = _window(text, m_moot.start(), m_moot.end())
        elif m_dismissed:
            non_merits_disposition = "dismissed"
            evidence["non_merits_signal"] = _window(text, m_dismissed.start(), m_dismissed.end())

    for key in ["1225", "1226", "bond hearing", "mandatory detention", "granted", "denied"]:
        idx = t.find(key)
        if idx != -1 and key not in evidence:
            evidence[key] = text[max(0, idx - 120): min(len(text), idx + 160)]

    holdings = {
        "applicable_provision": provision,
        "applicable_subprovision": subprovision,
        "bond_status": bond,
        "habeas_relief": habeas_relief,
    }

    if non_merits_disposition:
        holdings["non_merits_disposition"] = non_merits_disposition

    return holdings, evidence


def _extract_detention_location_flags(text: str) -> tuple[dict, dict]:
    t = _normalize(text)
    border_markers = [
        "at the border",
        "near the border",
        "southern border",
        "arriving alien",
        "port of entry",
        "arriving in the united states",
        "applicants for admission",
    ]
    interior_markers = [
        "within the country",
        "once inside the united states",
        "interior",
        "already here",
        "non-arriving alien",
        "non-arriving aliens",
        "within the territorial boundaries",
    ]

    border_hits = []
    for marker in border_markers:
        if marker in t:
            if marker == "arriving alien" and ("non-arriving alien" in t or "non-arriving aliens" in t):
                continue
            border_hits.append(marker)

    interior_hits = [m for m in interior_markers if m in t]

    is_border = len(border_hits) > 0 and len(interior_hits) == 0
    is_interior = len(interior_hits) > 0

    return {
        "is_border_or_near_border_detention": is_border if (border_hits or interior_hits) else None,
        "is_interior_detention_focus": is_interior if (border_hits or interior_hits) else None,
    }, {"border_hits": border_hits, "interior_hits": interior_hits}


def extract_case(text: str) -> ExtractedCase:
    if not isinstance(text, str):
        raise TypeError(f"extract_case expected str, got {type(text).__name__}")
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

    representation_status, representation_evidence = _extract_representation_status(t)
    evidence_spans["representation"] = {
        "status": representation_status,
        "evidence": representation_evidence,
    }

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

    confidence = 0.18 + (total_hits * 0.015)

    if holdings.get("applicable_provision"):
        confidence += 0.07
    if holdings.get("applicable_subprovision"):
        confidence += 0.04
    if holdings.get("bond_status"):
        confidence += 0.06
    if holdings.get("habeas_relief"):
        confidence += 0.06
    if representation_status and representation_status != "unknown":
        confidence += 0.03
    if flags.get("is_border_or_near_border_detention") is not None or flags.get("is_interior_detention_focus") is not None:
        confidence += 0.03

    # Penalize incomplete / defaulty-looking outputs
    if holdings.get("habeas_relief") is None:
        confidence -= 0.06
    if holdings.get("bond_status") is None:
        confidence -= 0.05
    if representation_status == "unknown":
        confidence -= 0.03

    if (
        holdings.get("applicable_provision") == "1226"
        and holdings.get("applicable_subprovision") == "1226(a)"
        and holdings.get("habeas_relief") is None
    ):
        confidence -= 0.08

    confidence = max(0.20, min(0.95, confidence))

    return ExtractedCase(
        petitioner_facts=petitioner_facts,
        petition_facts=petition_facts,
        respondent_position=respondent_position,
        reasoning_basis=reasoning_basis,
        precedent_citations=precedent_citations,
        holdings=holdings,
        phrase_signals=phrase_signals,
        representation_status=representation_status,
        representation_evidence=representation_evidence,
        evidence_spans=evidence_spans,
        flags=flags,
        confidence=confidence,
    )