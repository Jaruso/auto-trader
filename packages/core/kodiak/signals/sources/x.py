"""Playwright-backed X source collector."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from kodiak.errors import ConfigurationError
from kodiak.signals.models import SignalMonitorConfig, SignalSourceConfig, SourceItem
from kodiak.signals.x_api import XApiClient
from kodiak.signals.x_auth import load_x_oauth_credentials

STATUS_ID_RE = re.compile(r"/status/(\d+)")


class XSourceCollector:
    """Collect recent profile posts from X using a persisted login profile."""

    def collect(
        self,
        source: SignalSourceConfig,
        config: SignalMonitorConfig,
    ) -> list[SourceItem]:
        credentials = load_x_oauth_credentials()
        if credentials is not None:
            return self._collect_via_api(source, credentials, config)

        return self._collect_via_playwright(source, config)

    def _collect_via_api(
        self,
        source: SignalSourceConfig,
        credentials,
        config: SignalMonitorConfig,
    ) -> list[SourceItem]:
        del config
        items = XApiClient(credentials).fetch_home_timeline(max_results=source.max_posts * 4)
        account = source.account.lstrip("@").lower()
        return [item for item in items if item.author.lower() == account][: source.max_posts]

    def _collect_via_playwright(
        self,
        source: SignalSourceConfig,
        config: SignalMonitorConfig,
    ) -> list[SourceItem]:
        x_config = config.x
        if not x_config.enabled:
            raise ConfigurationError(
                message="X monitoring is disabled in market_signals.yaml",
                code="X_SOURCE_DISABLED",
            )
        if not x_config.user_data_dir:
            raise ConfigurationError(
                message="KODIAK_X_USER_DATA_DIR or x.user_data_dir is required for X monitoring",
                code="X_PROFILE_MISSING",
                suggestion=(
                    "Point Kodiak at a Playwright/Chromium user-data directory "
                    "that already contains a logged-in X session."
                ),
            )

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional runtime
            raise ConfigurationError(
                message="playwright is not installed for X monitoring",
                code="PLAYWRIGHT_MISSING",
                suggestion="Install the Python Playwright package and Chromium browser runtime.",
            ) from exc

        timeout_ms = x_config.timeout_seconds * 1000
        profile_url = f"https://x.com/{source.account.lstrip('@')}"
        items: list[SourceItem] = []
        seen_ids: set[str] = set()

        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=x_config.user_data_dir,
                    headless=x_config.headless,
                    executable_path=x_config.executable_path,
                )
                try:
                    page = context.new_page()
                    page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_selector("article", timeout=timeout_ms)

                    articles = page.locator("article")
                    article_count = min(articles.count(), source.max_posts)
                    for index in range(article_count):
                        article = articles.nth(index)
                        link_locator = article.locator("a[href*='/status/']").first
                        href = link_locator.get_attribute("href")
                        if not href:
                            continue
                        match = STATUS_ID_RE.search(href)
                        if not match:
                            continue
                        external_id = match.group(1)
                        if external_id in seen_ids:
                            continue
                        seen_ids.add(external_id)

                        time_locator = article.locator("time").first
                        published_raw = time_locator.get_attribute("datetime") or datetime.now(UTC).isoformat()
                        published_at = datetime.fromisoformat(
                            published_raw.replace("Z", "+00:00")
                        ).astimezone(UTC)
                        text = article.inner_text(timeout=timeout_ms).strip()
                        url = href if href.startswith("http") else f"https://x.com{href}"

                        items.append(
                            SourceItem(
                                external_id=external_id,
                                url=url,
                                published_at=published_at,
                                author=source.account.lstrip("@"),
                                text=text,
                            )
                        )
                finally:
                    context.close()
        except PlaywrightTimeoutError as exc:
            raise ConfigurationError(
                message=f"Timed out loading X profile page for @{source.account.lstrip('@')}",
                code="X_SOURCE_TIMEOUT",
            ) from exc

        return items
