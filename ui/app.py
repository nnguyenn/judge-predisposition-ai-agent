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
    with st.expander("ℹ️ What the outcome badges and review statuses mean", expanded=False):
        st.markdown(
            """
**Habeas Outcome (UI badge)**
- 🟢 **Granted** — Extractor found language indicating the habeas petition / writ was granted.
- 🔴 **Denied** — Extractor found language indicating the habeas petition / writ was denied.
- 🟡 **Partial** — Extractor found “granted in part / denied in part” style language.
- ⚪ **Unknown** — No extraction yet, insufficient text, or extractor could not confidently classify the outcome.

**Review Status**
- 🤖 **auto** — Auto-extracted and accepted by pipeline rules.
- ⚠️ **needs_review** — Low-confidence or ambiguous extraction; should be reviewed before relying on analytics.
- ✅ **reviewed** — Manually reviewed/approved.
- 🚫 **rejected** — Extraction rejected (excluded from analytics).

**Important**
- Judge score analytics include only cases marked **auto** or **reviewed**.
"""
        )


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
    top2.metric("Provision", detail.get("applicable_subprovision") or detail.get("applicable_provision") or "Unknown")
    top3.metric("Bond Status", detail.get("bond_status") or "Unknown")
    conf = detail.get("confidence")
    top4.metric("Confidence", f"{conf:.2f}" if isinstance(conf, (int, float)) else "N/A")

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
run_pipeline = row1a.button("Run Pipeline")
recompute_scores = row1b.button("Recompute Scores")

row2a, row2b = st.sidebar.columns(2)
extract_batch = row2a.button("Extract Batch")
retry_review_queue = row2b.button("Retry Review Queue")

batch_limit = st.sidebar.number_input(
    "Batch extract limit",
    min_value=1,
    max_value=1000,
    value=100,
    step=10,
)

review_retry_limit = st.sidebar.number_input(
    "Review retry limit",
    min_value=1,
    max_value=500,
    value=50,
    step=5,
)

if run_pipeline:
    try:
        result = api_post("/api/pipeline/run-once")
        st.sidebar.success("Pipeline completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Pipeline failed: {e}")

if recompute_scores:
    try:
        result = api_post("/api/scores/recompute")
        st.sidebar.success("Scores recomputed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Recompute failed: {e}")

if extract_batch:
    try:
        result = api_post("/api/extract/batch", params={"limit": int(batch_limit)})
        st.sidebar.success("Batch extraction completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Batch extract failed: {e}")

if retry_review_queue:
    try:
        result = api_post("/api/extract/review/retry", params={"limit": int(review_retry_limit)})
        st.sidebar.success("Review retry completed")
        st.sidebar.json(result)
    except Exception as e:
        st.sidebar.error(f"Review retry failed: {e}")

# ---------------------------
# Main page
# ---------------------------
st.title("⚖️ Habeas 1225/1226 Judge Pattern Tracker")
st.caption(
    "MVP UI for browsing cases, seeing habeas outcomes, reviewing extraction evidence, and checking judge-level trend scores."
)

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
    st.error(f"Failed to load cases: {e}")
    st.stop()

cases = payload.get("cases", [])
render_status_legend()

tab1, tab2, tab3 = st.tabs(["📚 Case Explorer", "🔍 Case Detail", "👩‍⚖️ Judge Summary"])

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
                "provision": c.get("applicable_subprovision") or c.get("applicable_provision"),
                "bond_status": c.get("bond_status"),
                "confidence": c.get("confidence"),
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
            rc1, rc2, rc3, rc4 = st.columns(4)
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

        except Exception as e:
            st.error(f"Failed to load case detail: {e}")

with tab3:
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