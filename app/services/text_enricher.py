from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

from app.config import settings
from app.models import CaseRecord


def _clean_text(text: str | None) -> str | None:
    if not text:
        return None
    t = text
    t = html.unescape(t)
    t = re.sub(r"<script[\s\S]*?</script>", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)  # strip remaining tags
    t = re.sub(r"\r", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = t.strip()
    return t or None

def _parse_courtlistener_opinion_id(case: CaseRecord) -> int | None:
    """
    Extract CourtListener opinion ID from relative/absolute opinion_url like:
    /opinion/7336569/padilla-v-.../
    """
    candidates = []

    if case.opinion_url:
        candidates.append(case.opinion_url)

    payload = case.retrieval_payload or {}
    for k in ["absolute_url", "url", "opinion_url"]:
        v = payload.get(k)
        if isinstance(v, str):
            candidates.append(v)

    for u in candidates:
        m = re.search(r"/opinion/(\d+)/", u)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _courtlistener_opinion_api_url(opinion_id: int) -> str:
    base = settings.retrieval_base_url.rstrip("/")
    return f"{base}/api/rest/v4/opinions/{opinion_id}/"


def _extract_text_from_courtlistener_opinion_api_json(data: dict) -> tuple[str | None, str]:
    """
    CourtListener opinions API often exposes multiple text/html variants.
    Prefer html_with_citations first, then fall back to plain_text.
    """
    candidate_fields = [
        "html_with_citations",
        "plain_text",
        "html",
        "html_lawbox",
        "html_columbia",
        "html_anon_2020",
    ]

    for field in candidate_fields:
        v = data.get(field)
        if isinstance(v, str) and v.strip():
            cleaned = _clean_text(v)
            if _looks_like_opinion_text(cleaned):
                return cleaned, f"courtlistener-opinion-api:{field}"

    return None, "courtlistener-opinion-api:no_usable_text"

def _looks_like_opinion_text(text: str | None) -> bool:
    if not text:
        return False
    # Very loose heuristic: long enough + contains legal-ish cues
    if len(text) < 300:
        return False
    t = text.lower()
    signals = [
        "petition", "habeas", "court", "respondent", "detention",
        "§ 1225", "§ 1226", "bond hearing", "ordered", "granted", "denied"
    ]
    return any(s in t for s in signals)


def _safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _candidate_strings_from_payload(payload: dict | None) -> list[tuple[str, str]]:
    """
    Returns (source_label, text) candidates from the stored retrieval payload.
    """
    if not payload:
        return []

    out: list[tuple[str, str]] = []

    keys = [
        "plain_text",
        "text",
        "snippet",
        "html",
        "html_with_citations",
        "opinion_text",
    ]
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            out.append((f"payload:{k}", v))

    # Sometimes nested structures appear
    for nested_key in ["opinion", "cluster", "document", "result"]:
        nv = payload.get(nested_key)
        if isinstance(nv, dict):
            for k in keys:
                v = nv.get(k)
                if isinstance(v, str) and v.strip():
                    out.append((f"payload:{nested_key}.{k}", v))

    return out


def _candidate_urls_from_case(case: CaseRecord) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []

    # Primary columns
    if case.opinion_url:
        urls.append(("case.opinion_url", case.opinion_url))
    if case.docket_url:
        urls.append(("case.docket_url", case.docket_url))

    payload = case.retrieval_payload or {}
    # Common URL-ish fields
    url_keys = [
        "absolute_url",
        "download_url",
        "url",
        "html_url",
        "plain_text_url",
        "opinion_url",
    ]
    for k in url_keys:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            urls.append((f"payload:{k}", v))

    # De-dup preserve order
    seen = set()
    deduped = []
    for label, u in urls:
        key = u.strip()
        if key not in seen:
            seen.add(key)
            deduped.append((label, key))
    return deduped


def _to_absolute_url(url: str) -> str:
    u = url.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("/"):
        return settings.retrieval_base_url.rstrip("/") + u
    return u


def _extract_text_from_html_body(raw_html: str) -> str | None:
    # First try <article> if present
    m_article = re.search(r"<article\b[^>]*>([\s\S]*?)</article>", raw_html, flags=re.IGNORECASE)
    if m_article:
        t = _clean_text(m_article.group(1))
        if _looks_like_opinion_text(t):
            return t

    # Try common content containers
    patterns = [
        r'<div[^>]+id="[^"]*opinion[^"]*"[^>]*>([\s\S]*?)</div>',
        r'<div[^>]+class="[^"]*(?:opinion-text|opinion|document|case-text|col-main|content-body)[^"]*"[^>]*>([\s\S]*?)</div>',
        r'<pre\b[^>]*>([\s\S]*?)</pre>',
        r'<main\b[^>]*>([\s\S]*?)</main>',
        r'<body\b[^>]*>([\s\S]*?)</body>',
    ]
    for p in patterns:
        m = re.search(p, raw_html, flags=re.IGNORECASE)
        if not m:
            continue
        t = _clean_text(m.group(1))
        if _looks_like_opinion_text(t):
            return t

    # Fallback: whole page stripped (noisy, but better than nothing if legal signals present)
    t = _clean_text(raw_html)
    if _looks_like_opinion_text(t):
        return t
    return None


def _extract_text_from_http_response(resp: httpx.Response) -> tuple[str | None, str]:
    content_type = (resp.headers.get("content-type") or "").lower()

    # JSON response (sometimes APIs return nested fields)
    if "application/json" in content_type:
        data = _safe_json_loads(resp.text)
        if isinstance(data, dict):
            for label, candidate in _candidate_strings_from_payload(data):
                cleaned = _clean_text(candidate)
                if _looks_like_opinion_text(cleaned):
                    return cleaned, f"http-json:{label}"
        return None, "http-json:no_usable_text"

    # HTML page
    if "text/html" in content_type or "<html" in resp.text.lower():
        text = _extract_text_from_html_body(resp.text)
        if text:
            return text, "http-html"
        return None, "http-html:no_usable_text"

    # Plain text endpoint
    if "text/plain" in content_type:
        text = _clean_text(resp.text)
        if _looks_like_opinion_text(text):
            return text, "http-plain"
        return None, "http-plain:no_usable_text"

    # PDF / binary not handled in this MVP patch
    if "application/pdf" in content_type:
        return None, "pdf_not_supported_yet"

    # Fallback
    text = _clean_text(resp.text)
    if _looks_like_opinion_text(text):
        return text, "http-fallback"
    return None, "http:no_usable_text"

def _parse_courtlistener_cluster_id(case: CaseRecord) -> int | None:
    # Prefer explicit source_cluster_id if present
    if case.source_cluster_id:
        try:
            return int(str(case.source_cluster_id))
        except Exception:
            pass

    candidates = []
    if case.opinion_url:
        candidates.append(case.opinion_url)

    payload = case.retrieval_payload or {}
    for k in ["absolute_url", "url", "opinion_url"]:
        v = payload.get(k)
        if isinstance(v, str):
            candidates.append(v)

    for u in candidates:
        m = re.search(r"/opinion/(\d+)/", u)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def _courtlistener_cluster_api_url(cluster_id: int) -> str:
    base = settings.retrieval_base_url.rstrip("/")
    return f"{base}/api/rest/v4/clusters/{cluster_id}/"


def _extract_text_from_courtlistener_cluster_json(data: dict) -> tuple[str | None, str]:
    """
    Some cluster payloads may include text/html variants directly.
    Prefer html_with_citations first, then plain_text.
    """
    candidate_fields = [
        "html_with_citations",
        "plain_text",
        "html",
        "html_lawbox",
        "html_columbia",
        "html_anon_2020",
    ]
    for field in candidate_fields:
        v = data.get(field)
        if isinstance(v, str) and v.strip():
            cleaned = _clean_text(v)
            if _looks_like_opinion_text(cleaned):
                return cleaned, f"courtlistener-cluster-api:{field}"
    return None, "courtlistener-cluster-api:no_direct_text"


def _extract_sub_opinion_refs_from_cluster(data: dict) -> list[str]:
    """
    Returns URLs or IDs for sub opinions from cluster payload.
    Handles a few common shapes.
    """
    refs: list[str] = []

    for key in ["sub_opinions", "opinions"]:
        v = data.get(key)

        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    refs.append(item.strip())
                elif isinstance(item, int):
                    refs.append(str(item))
                elif isinstance(item, dict):
                    # if nested objects happen
                    for k in ["url", "resource_uri", "id"]:
                        iv = item.get(k)
                        if iv is not None:
                            refs.append(str(iv))
                            break

    # de-dupe
    seen = set()
    out = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _courtlistener_opinion_api_url_from_ref(ref: str) -> str:
    base = settings.retrieval_base_url.rstrip("/")
    ref = ref.strip()

    # already full URL
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref

    # API relative URL
    if ref.startswith("/api/"):
        return base + ref

    # plain numeric id
    if ref.isdigit():
        return f"{base}/api/rest/v4/opinions/{ref}/"

    # fallback
    return ref


def enrich_case_text(case: CaseRecord, timeout: float = 20.0, overwrite: bool = False) -> dict:
    """
    Attempt to populate case.opinion_text from:
    1) strong existing retrieval payload strings
    2) CourtListener cluster API
    3) CourtListener opinion API objects from cluster refs
    4) generic URL fetching as a last resort

    Returns a status dict (does not commit DB session).
    """
    if case.opinion_text and case.opinion_text.strip() and not overwrite:
        return {"status": "already_has_text", "source": "db"}

    headers = {}
    api_key = getattr(settings, "effective_retrieval_api_key", None)
    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    # 1) Try only stronger payload text first.
    # Intentionally do NOT use snippet/text here as primary enrichment sources.
    payload = case.retrieval_payload or {}
    strong_payload_keys = [
        "html_with_citations",
        "plain_text",
        "html",
        "opinion_text",
    ]
    for k in strong_payload_keys:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            cleaned = _clean_text(v)
            if _looks_like_opinion_text(cleaned):
                case.opinion_text = cleaned
                if not case.text_excerpt:
                    case.text_excerpt = cleaned[:500]
                return {"status": "enriched", "source": f"payload:{k}", "length": len(cleaned)}

    # 2) CourtListener cluster API first
    cluster_id = _parse_courtlistener_cluster_id(case)
    if cluster_id is not None:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                cluster_url = _courtlistener_cluster_api_url(cluster_id)
                cluster_resp = client.get(cluster_url)

                if cluster_resp.status_code < 400:
                    cluster_data = _safe_json_loads(cluster_resp.text)
                    if isinstance(cluster_data, dict):
                        # direct text on cluster
                        text, source_kind = _extract_text_from_courtlistener_cluster_json(cluster_data)
                        if text:
                            case.opinion_text = text
                            if not case.text_excerpt:
                                case.text_excerpt = text[:500]
                            return {"status": "enriched", "source": source_kind, "length": len(text)}

                        # then sub-opinion refs
                        refs = _extract_sub_opinion_refs_from_cluster(cluster_data)
                        for ref in refs:
                            opinion_api_url = _courtlistener_opinion_api_url_from_ref(ref)
                            try:
                                op_resp = client.get(opinion_api_url)
                                if op_resp.status_code >= 400:
                                    continue
                                op_data = _safe_json_loads(op_resp.text)
                                if not isinstance(op_data, dict):
                                    continue

                                text, source_kind = _extract_text_from_courtlistener_opinion_api_json(op_data)
                                if text:
                                    case.opinion_text = text
                                    if not case.text_excerpt:
                                        case.text_excerpt = text[:500]
                                    return {"status": "enriched", "source": source_kind, "length": len(text)}
                            except Exception:
                                continue
        except Exception:
            pass

    # 3) As a cheaper fallback, try payload-derived full text again more broadly
    for source_label, candidate in _candidate_strings_from_payload(case.retrieval_payload):
        cleaned = _clean_text(candidate)
        if _looks_like_opinion_text(cleaned):
            case.opinion_text = cleaned
            if not case.text_excerpt:
                case.text_excerpt = cleaned[:500]
            return {"status": "enriched", "source": source_label, "length": len(cleaned)}

    # 4) Generic URL fallback LAST
    urls = _candidate_urls_from_case(case)
    if not urls:
        return {"status": "no_url", "source": None}

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        last_reason = None
        for label, raw_url in urls:
            url = _to_absolute_url(raw_url)
            try:
                resp = client.get(url)
                if resp.status_code >= 400:
                    last_reason = f"http_{resp.status_code}"
                    continue

                text, source_kind = _extract_text_from_http_response(resp)
                if text:
                    case.opinion_text = text
                    if not case.text_excerpt:
                        case.text_excerpt = text[:500]
                    return {"status": "enriched", "source": f"{label}|{source_kind}", "length": len(text)}
                else:
                    last_reason = source_kind
            except Exception as e:
                last_reason = f"request_error:{type(e).__name__}:{e}"

    return {"status": "no_usable_text_found", "source": last_reason}


def batch_enrich_text(
    db,
    limit: int = 50,
    overwrite: bool = False,
    timeout: float = 20.0,
) -> dict:
    """
    Enriches cases missing opinion_text. Commits updates.
    """
    from sqlalchemy import select, or_  # local import to avoid circulars if any

    stmt = (
        select(CaseRecord)
        .where(
            or_(
                CaseRecord.opinion_text.is_(None),
                CaseRecord.opinion_text == "",
            )
        )
        .order_by(CaseRecord.decision_date.desc().nullslast(), CaseRecord.id.desc())
        .limit(limit)
    )
    cases = db.execute(stmt).scalars().all()

    stats = {
        "selected": len(cases),
        "enriched": 0,
        "already_has_text": 0,
        "no_url": 0,
        "no_usable_text_found": 0,
        "error": 0,
        "details": [],
    }

    for case in cases:
        try:
            result = enrich_case_text(case, timeout=timeout, overwrite=overwrite)
            status = result.get("status", "error")
            stats[status] = stats.get(status, 0) + 1
            stats["details"].append({
                "case_id": case.id,
                "case_caption": case.case_caption,
                **result,
            })
        except Exception as e:
            stats["error"] += 1
            stats["details"].append({
                "case_id": case.id,
                "case_caption": case.case_caption,
                "status": "error",
                "error": str(e),
            })

    db.commit()
    return stats