from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "dev"
    database_url: str

    retrieval_base_url: str = "https://www.courtlistener.com"
    retrieval_search_path: str = "/api/rest/v4/search/"
    retrieval_api_key: str | None = None

    poll_query: str = 'habeas 1225 1226 "mandatory detention" "bond hearing"'
    poll_lookback_days: int = 14
    poll_max_results: int = 25

    # Agent loop / scheduler
    enable_scheduler: bool = False
    scheduler_interval_minutes: int = 30

    # Extraction pipeline behavior
    extraction_batch_limit: int = 50
    auto_review_confidence_threshold: float = 0.45
    require_opinion_text_for_auto_extract: bool = False  # if True, skip snippet-only cases


settings = Settings()