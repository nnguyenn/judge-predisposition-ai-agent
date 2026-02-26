from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import sqrt
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import CaseRecord, CaseExtraction, JudgeIssueScore


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def recompute_judge_scores(db: Session, as_of: date | None = None) -> int:
    """
    MVP empirical-Bayes-ish smoothing:
    smoothed_rate = (successes + alpha) / (n + alpha + beta)
    """
    if as_of is None:
        as_of = date.today()

    rows = db.execute(
        select(CaseRecord, CaseExtraction)
        .join(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .where(CaseRecord.judge_name.is_not(None))
        .where(CaseExtraction.review_status.in_(["auto", "reviewed"]))
    ).all()

    # Global priors
    global_n = 0
    g_1226 = g_bond = g_habeas = 0

    parsed = []
    for case, ext in rows:
        h = ext.holdings or {}
        parsed.append((case, ext, h))

        global_n += 1
        if h.get("applicable_provision") == "1226":
            g_1226 += 1
        if h.get("bond_status") == "eligible":
            g_bond += 1
        if h.get("habeas_relief") in {"granted", "granted_in_part", "granted_in_part_and_denied_in_part"}:
            g_habeas += 1

    if global_n == 0:
        return 0

    global_rate_1226 = g_1226 / global_n
    global_rate_bond = g_bond / global_n
    global_rate_habeas = g_habeas / global_n

    # Prior strength (tune later)
    prior_strength = 5.0

    buckets = defaultdict(list)
    for case, ext, h in parsed:
        judge = (case.judge_name or "").strip()
        if not judge:
            continue
        buckets[(judge, "all")].append((case, ext, h))
        if ext.is_interior_detention_focus:
            buckets[(judge, "interior_detention")].append((case, ext, h))
        if ext.is_border_or_near_border_detention:
            buckets[(judge, "near_border")].append((case, ext, h))

    # replace existing snapshot for same day (simple approach)
    db.query(JudgeIssueScore).filter(JudgeIssueScore.as_of_date == as_of).delete()

    created = 0
    for (judge, segment), items in buckets.items():
        n = len(items)
        s1226 = sum(1 for _, _, h in items if h.get("applicable_provision") == "1226")
        sbond = sum(1 for _, _, h in items if h.get("bond_status") == "eligible")
        shab = sum(1 for _, _, h in items if h.get("habeas_relief") in {"granted", "granted_in_part", "granted_in_part_and_denied_in_part"})

        # Smoothed rates
        r1226 = (s1226 + prior_strength * global_rate_1226) / (n + prior_strength)
        rbond = (sbond + prior_strength * global_rate_bond) / (n + prior_strength)
        rhab = (shab + prior_strength * global_rate_habeas) / (n + prior_strength)

        ci_low, ci_high = _wilson_interval(s1226, n)

        db.add(JudgeIssueScore(
            judge_name=judge,
            as_of_date=as_of,
            segment=segment,
            n_cases=n,
            rate_1226=r1226,
            rate_bond_eligible=rbond,
            rate_habeas_granted=rhab,
            ci_low=ci_low,
            ci_high=ci_high,
            model_meta={
                "prior_strength": prior_strength,
                "global_rate_1226": global_rate_1226,
                "global_rate_bond": global_rate_bond,
                "global_rate_habeas": global_rate_habeas,
                "note": "Descriptive issue-specific tendency score (not motive inference)"
            }
        ))
        created += 1

    db.commit()
    return created