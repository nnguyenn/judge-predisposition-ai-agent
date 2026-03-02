import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Habeas 1225/1226 Judge Tracker",
    page_icon="⚖️",
    layout="wide",
)

DEFAULT_API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def api_get(path: str, params: dict | None = None, timeout: float = 20.0) -> Any:
    base = st.session_state.get("api_base_url", DEFAULT_API_BASE).rstrip("/")
    url = f"{base}{path}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def api_post(path: str, params: dict | None = None, timeout: float = 60.0) -> Any:
    base = st.session_state.get("api_base_url", DEFAULT_API_BASE).rstrip("/")
    url = f"{base}{path}"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, params=params)
        resp.raise_for_status()
        return resp.json()

def user_friendly_api_error(e: Exception) -> str:
    msg = str(e)

    # Friendly explanation for metadata-only cases (no text to extract)
    if "400 Bad Request" in msg and "/extract" in msg:
        return (
            "This case cannot be analyzed yet because no opinion text/snippet is currently available. "
            "It appears to be a metadata-only record at the moment."
        )

    return msg


def outcome_badge(outcome: str | None) -> str:
    outcome = (outcome or "unknown").lower()
    if outcome == "granted":
        return "🟢 Granted"
    if outcome == "denied":
        return "🔴 Denied"
    if outcome == "partial":
        return "🟡 Partial"
    return "⚪ Unknown"


def review_badge(status: str | None) -> str:
    status = (status or "none").lower()
    if status == "reviewed":
        return "✅ reviewed"
    if status == "auto":
        return "🤖 auto"
    if status == "needs_review":
        return "⚠️ needs_review"
    if status == "rejected":
        return "🚫 rejected"
    return "—"


def safe_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def render_status_legend():
    with st.expander("ℹ️ What the outcomes and review statuses mean", expanded=False):
        st.markdown(
            """
**Habeas Outcome**
- 🟢 **Granted** — The extractor found language indicating the habeas petition / writ was granted.
- 🔴 **Denied** — The extractor found language indicating the habeas petition / writ was denied.
- 🟡 **Partial** — The extractor found “granted in part / denied in part” language.
- ⚪ **Unknown** — No analysis yet, insufficient case text, or the extractor could not classify the outcome.

**Review Status**
- 🤖 **Auto** — Automatically analyzed and accepted by current rules.
- ⚠️ **Needs Review** — Low-confidence or ambiguous result; should be checked before relying on analytics.
- ✅ **Reviewed** — Manually reviewed/approved.
- 🚫 **Rejected** — Analysis rejected and excluded from analytics.

**Historical Judge Pattern Metrics**
- Judge summary metrics are based only on cases marked **Auto** or **Reviewed**.
"""
        )

def render_cases_needing_review():
    st.markdown("### Cases Needing Review")
    st.caption("These are analyzed cases flagged for manual review before they are used in judge pattern analytics.")

    try:
        rows = api_get("/api/review/queue", params={"limit": 200})
    except Exception as e:
        st.error(f"Could not load review queue: {user_friendly_api_error(e)}")
        return

    if not rows:
        st.success("No cases are currently flagged for review.")
        return

    table_rows = []
    for r in rows:
        holdings = r.get("holdings") or {}
        raw_relief = (holdings.get("habeas_relief") or "").lower()
        if "granted_in_part" in raw_relief or "denied_in_part" in raw_relief or "in part" in raw_relief:
            outcome = "partial"
        elif raw_relief == "granted":
            outcome = "granted"
        elif raw_relief == "denied":
            outcome = "denied"
        else:
            outcome = "unknown"

        table_rows.append({
            "case_id": r.get("case_id"),
            "date": r.get("decision_date"),
            "case_caption": r.get("case_caption"),
            "judge": r.get("judge_name"),
            "court": r.get("court"),
            "habeas_outcome": outcome_badge(outcome),
            "detention_classification": holdings.get("applicable_subprovision") or holdings.get("applicable_provision"),
            "bond_status": holdings.get("bond_status"),
            "extraction_confidence": r.get("confidence"),
            "review_status": review_badge(r.get("review_status")),
        })

    df = pd.DataFrame(table_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("#### Review actions")
    selected_case_id = st.selectbox(
        "Select a flagged case",
        options=[r["case_id"] for r in rows],
        format_func=lambda cid: next(
            (f"{x['case_id']} • {x.get('case_caption') or 'Untitled'}" for x in rows if x["case_id"] == cid),
            str(cid)
        ),
        key="review_queue_case_select",
    )

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Mark Auto", key="rq_mark_auto"):
        try:
            api_post(f"/api/review/{selected_case_id}/mark", params={"status": "auto"})
            st.success("Marked Auto")
            st.rerun()
        except Exception as e:
            st.error(user_friendly_api_error(e))

    if c2.button("Mark Reviewed", key="rq_mark_reviewed"):
        try:
            api_post(f"/api/review/{selected_case_id}/mark", params={"status": "reviewed"})
            st.success("Marked Reviewed")
            st.rerun()
        except Exception as e:
            st.error(user_friendly_api_error(e))

    if c3.button("Reject", key="rq_mark_rejected"):
        try:
            api_post(f"/api/review/{selected_case_id}/mark", params={"status": "rejected"})
            st.warning("Marked Rejected")
            st.rerun()
        except Exception as e:
            st.error(user_friendly_api_error(e))

    if c4.button("Reanalyze Selected", key="rq_reextract_one"):
        try:
            api_post(f"/api/cases/{selected_case_id}/extract")
            st.success("Case reanalyzed")
            st.rerun()
        except Exception as e:
            st.error(user_friendly_api_error(e))


def render_case_summary_metrics(cases: list[dict]):
    granted = sum(1 for c in cases if c.get("habeas_outcome") == "granted")
    denied = sum(1 for c in cases if c.get("habeas_outcome") == "denied")
    partial = sum(1 for c in cases if c.get("habeas_outcome") == "partial")
    unknown = sum(1 for c in cases if c.get("habeas_outcome") == "unknown")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Cases", len(cases))
    c2.metric("Granted", granted)
    c3.metric("Denied", denied)
    c4.metric("Partial", partial)
    c5.metric("Unknown", unknown)


def render_case_detail(detail: dict):
    st.subheader(detail.get("case_caption") or f"Case {detail.get('case_id')}")

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Habeas Outcome", outcome_badge(detail.get("habeas_outcome")))
    top2.metric("Detention Classification", detail.get("applicable_subprovision") or detail.get("applicable_provision") or "Unknown")
    top3.metric("Bond Hearing", detail.get("bond_status") or "Unknown")
    conf = detail.get("confidence")
    top4.metric("Extraction Confidence", f"{conf:.2f}" if isinstance(conf, (int, float)) else "N/A")

    meta_cols = st.columns(4)
    meta_cols[0].write(f"**Judge:** {detail.get('judge_name') or 'Unknown'}")
    meta_cols[1].write(f"**Court:** {detail.get('court') or 'Unknown'}")
    meta_cols[2].write(f"**Decision date:** {detail.get('decision_date') or 'Unknown'}")
    meta_cols[3].write(f"**Review:** {review_badge(detail.get('review_status'))}")

    if detail.get("opinion_url"):
        st.markdown(f"[Open opinion URL]({detail['opinion_url']})")

    st.divider()

    left, right = st.columns([1.25, 1])

    with left:
        st.markdown("### Holdings")
        st.json(detail.get("holdings") or {})

        st.markdown("### Reasoning Basis")
        st.json(detail.get("reasoning_basis") or {})

        st.markdown("### Flags")
        st.json({
            "is_border_or_near_border_detention": detail.get("is_border_or_near_border_detention"),
            "is_interior_detention_focus": detail.get("is_interior_detention_focus"),
        })

    with right:
        st.markdown("### Evidence Spans")
        st.json(detail.get("evidence_spans") or {})

        st.markdown("### Opinion Text Preview")
        preview = detail.get("opinion_text_preview") or detail.get("text_excerpt") or "(No text available)"
        st.code(preview[:3000])

    with st.expander("Advanced extraction fields"):
        st.markdown("#### Petitioner Facts")
        st.json(detail.get("petitioner_facts") or {})
        st.markdown("#### Petition Facts")
        st.json(detail.get("petition_facts") or {})
        st.markdown("#### Respondent Position")
        st.json(detail.get("respondent_position") or {})
        st.markdown("#### Precedent Citations")
        st.json(detail.get("precedent_citations") or {})


def render_judge_scores(judge_name: str):
    st.markdown(f"### Judge Pattern Scores — {judge_name}")
    try:
        rows = api_get(f"/api/judges/{judge_name}/scores")
    except Exception as e:
        st.error(f"Could not load judge scores: {e}")
        return

    if not rows:
        st.info("No scores found for this judge yet (or cases may be excluded by review status).")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # Show latest "all" segment as quick summary
    latest_date = df["as_of_date"].max()
    latest = df[df["as_of_date"] == latest_date]
    all_row = latest[latest["segment"] == "all"]
    if not all_row.empty:
        r = all_row.iloc[0]
        a, b, c, d = st.columns(4)
        a.metric("Cases (all)", int(r["n_cases"]))
        a2 = r["rate_habeas_granted"]
        b.metric("Habeas Granted Rate", f"{a2:.2f}" if pd.notna(a2) else "N/A")
        c2 = r["rate_1226"]
        c.metric("1226 Rate", f"{c2:.2f}" if pd.notna(c2) else "N/A")
        d2 = r["rate_bond_eligible"]
        d.metric("Bond Eligible Rate", f"{d2:.2f}" if pd.notna(d2) else "N/A")

def render_law_friendly_intro():
    st.markdown(
        """
This tool helps track **historical judicial ruling patterns** on the **§1225 / §1226 habeas detention issue**.

It can:
- identify whether **habeas relief was granted, denied, or partially granted**
- classify the detention issue (**1225 vs 1226**)
- show supporting evidence snippets from the case text
- summarize **judge-level historical patterns** based on past analyzed cases

"""
    )
    st.caption(
        "Results are descriptive research analytics based on extracted case text (not legal advice). "
        "Cases marked 'Needs Review' should be checked before relying on trend metrics."
    )


# ---------------------------
# Sidebar controls
# ---------------------------
st.sidebar.title("⚙️ Controls")

st.session_state["api_base_url"] = st.sidebar.text_input(
    "Backend API Base URL",
    value=st.session_state.get("api_base_url", DEFAULT_API_BASE),
    help="FastAPI server base URL",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Filters")

judge_filter = st.sidebar.text_input("Judge name contains", value="")
outcome_filter_label = st.sidebar.selectbox(
    "Habeas outcome",
    options=["All", "Granted", "Denied", "Partial", "Unknown"],
    index=0,
)
review_filter_label = st.sidebar.selectbox(
    "Review status",
    options=["All", "auto", "needs_review", "reviewed", "rejected"],
    index=0,
)
limit = st.sidebar.slider("Max cases", min_value=10, max_value=500, value=100, step=10)

st.sidebar.markdown("---")
st.sidebar.markdown("### Actions")

row1a, row1b = st.sidebar.columns(2)
run_pipeline = row1a.button("Check for New Cases")
recompute_scores = row1b.button("Refresh Judge Metrics")

row2a, row2b = st.sidebar.columns(2)
extract_batch = row2a.button("Analyze Available Cases")
retry_review_queue = row2b.button("Reanalyze Flagged Cases")

row3a, row3b = st.sidebar.columns(2)
enrich_text_batch = row3a.button("Fetch Opinion Text")
enrich_limit = st.sidebar.number_input(
    "Opinion-text fetch limit",
    min_value=1,
    max_value=1000,
    value=50,
    step=10,
)

batch_limit = st.sidebar.number_input(
    "Analyze case limit",
    min_value=1,
    max_value=1000,
    value=100,
    step=10,
)

review_retry_limit = st.sidebar.number_input(
    "Flagged-case reanalysis limit",
    min_value=1,
    max_value=500,
    value=50,
    step=5,
)

if run_pipeline:
    try:
        result = api_post("/api/pipeline/run-once")
        st.sidebar.success("Case check completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Case check failed: {user_friendly_api_error(e)}")

if enrich_text_batch:
    try:
        result = api_post("/api/enrich/text/batch", params={"limit": int(enrich_limit)})
        st.sidebar.success("Opinion text fetch completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(user_friendly_api_error(e))

if recompute_scores:
    try:
        result = api_post("/api/scores/recompute")
        st.sidebar.success("Judge metrics refreshed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Refresh failed: {user_friendly_api_error(e)}")

if extract_batch:
    try:
        result = api_post("/api/extract/batch", params={"limit": int(batch_limit)})
        st.sidebar.success("Analysis completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Analysis failed: {user_friendly_api_error(e)}")

if retry_review_queue:
    try:
        result = api_post("/api/extract/review/retry", params={"limit": int(review_retry_limit)})
        st.sidebar.success("Flagged cases reanalyzed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Reanalysis failed: {user_friendly_api_error(e)}")

# ---------------------------
# Main page
# ---------------------------
st.title("⚖️ Habeas 1225/1226 Judicial Pattern Tracker")
render_law_friendly_intro()

# Health check
try:
    health = api_get("/api/health")
    if health.get("ok"):
        st.success("Backend connected")
except Exception as e:
    st.error(f"Cannot connect to backend: {e}")
    st.stop()

# Load UI-friendly case list
params = {"limit": limit}
if judge_filter.strip():
    params["judge_name"] = judge_filter.strip()

if outcome_filter_label != "All":
    params["habeas_outcome"] = outcome_filter_label.lower()

if review_filter_label != "All":
    params["review_status"] = review_filter_label

try:
    payload = api_get("/api/ui/cases", params=params)
    
except Exception as e:
    st.error(user_friendly_api_error(e))

cases = payload.get("cases", [])
render_status_legend()

tab1, tab2, tab3, tab4 = st.tabs([
    "📚 Case List",
    "🔍 Case Detail",
    "⚠️ Cases Needing Review",
    "👩‍⚖️ Historical Judge Patterns",
])

with tab1:
    st.markdown("### Cases")
    if not cases:
        st.info("No cases match the current filters.")
    else:
        table_rows = []
        for c in cases:
            table_rows.append({
                "case_id": c["case_id"],
                "date": c.get("decision_date"),
                "case_caption": c.get("case_caption"),
                "judge": c.get("judge_name"),
                "court": c.get("court"),
                "habeas_outcome": outcome_badge(c.get("habeas_outcome")),
                "detention_classification": c.get("applicable_subprovision") or c.get("applicable_provision"),
                "bond_status": c.get("bond_status"),
                "extraction_confidence": c.get("confidence"),
                "review_status": review_badge(c.get("review_status")),
                "has_extraction": c.get("has_extraction"),
            })

        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        selected_case = st.selectbox(
            "Select a case to inspect",
            options=cases,
            format_func=lambda c: f"{c['case_id']} • {c.get('case_caption') or 'Untitled'}"
                                  f" • {c.get('judge_name') or 'Unknown judge'}"
                                  f" • {outcome_badge(c.get('habeas_outcome'))}",
            key="selected_case_obj",
        )

        if selected_case:
            st.session_state["selected_case_id"] = selected_case["case_id"]

with tab2:
    selected_case_id = st.session_state.get("selected_case_id")
    if not selected_case_id and cases:
        selected_case_id = cases[0]["case_id"]
        st.session_state["selected_case_id"] = selected_case_id

    if not selected_case_id:
        st.info("Select a case in the Case Explorer tab.")
    else:
        try:
            detail = api_get(f"/api/ui/cases/{selected_case_id}")
            render_case_detail(detail)

            # quick review controls
            st.markdown("### Review Controls")
            rc1, rc2, rc3, rc4, rc5 = st.columns(5)
            if rc1.button("Mark auto", key=f"mark_auto_{selected_case_id}"):
                api_post(f"/api/review/{selected_case_id}/mark", params={"status": "auto"})
                st.success("Marked auto")
                st.rerun()
            if rc2.button("Mark needs_review", key=f"mark_nr_{selected_case_id}"):
                api_post(f"/api/review/{selected_case_id}/mark", params={"status": "needs_review"})
                st.warning("Marked needs_review")
                st.rerun()
            if rc3.button("Mark reviewed", key=f"mark_rev_{selected_case_id}"):
                api_post(f"/api/review/{selected_case_id}/mark", params={"status": "reviewed"})
                st.success("Marked reviewed")
                st.rerun()
            if rc4.button("Extract / Re-extract Case", key=f"rex_{selected_case_id}"):
                api_post(f"/api/cases/{selected_case_id}/extract")
                st.success("Re-extracted case")
                st.rerun()
            if rc5.button("Fetch Opinion Text", key=f"enrich_{selected_case_id}"):
              try:
                  api_post(f"/api/cases/{selected_case_id}/enrich-text")
                  st.success("Opinion text fetch attempted")
                  st.rerun()
              except Exception as e:
                  st.error(user_friendly_api_error(e))

        except Exception as e:
            st.error(user_friendly_api_error(e))

with tab3:
    render_cases_needing_review()

with tab4:
    # derive default judge from selected case
    selected_case_id = st.session_state.get("selected_case_id")
    default_judge = ""
    if selected_case_id:
        selected = next((c for c in cases if c["case_id"] == selected_case_id), None)
        if selected and selected.get("judge_name"):
            default_judge = selected["judge_name"]

    judge_query = st.text_input(
        "Judge name (partial match supported by backend endpoint)",
        value=default_judge or (judge_filter.strip() if judge_filter.strip() else "Judge Alpha"),
        key="judge_query",
    )

    if st.button("Load Judge Scores"):
        st.session_state["judge_query_submit"] = judge_query

    judge_to_show = st.session_state.get("judge_query_submit", judge_query)

    if judge_to_show:
        render_judge_scores(judge_to_show)