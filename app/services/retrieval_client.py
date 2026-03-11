# app/services/retrieval_client.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import httpx
from app.config import settings


class RetrievalClient:
    """
    Generic retrieval client wrapper.
    Default config points to CourtListener-style search, but path/query can be changed via env.
    """

    def __init__(self):
        self.base_url = settings.retrieval_base_url.rstrip("/")
        self.search_path = settings.retrieval_search_path
        self.api_key = settings.effective_retrieval_api_key

    def search_recent_cases(self, query: str, lookback_days: int = 14, page_size: int = 25) -> list[dict]:
        url = f"{self.base_url}{self.search_path}"
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"

        params = {
            "q": query,
            "page_size": page_size,
            "type": "o",
            "order_by": "dateFiled desc",
            "date_filed_min": since,
        }

        with httpx.Client(timeout=30.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], list):
                return data["results"]
            if "objects" in data and isinstance(data["objects"], list):
                return data["objects"]

        if isinstance(data, list):
            return data

        return []