"""HTML loaders for live usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode

from .exceptions import OpenScreenerError


@dataclass(slots=True)
class PlaywrightScraper:
    """Live HTML loader that fetches Screener pages through rustwright."""

    base_url: str = "https://www.screener.in/company/{symbol}{path_suffix}"
    consolidated: bool = False
    headless: bool = True
    timeout_ms: int = 30000

    def fetch_page(self, symbol: str) -> str:
        with self._browser_session() as browser:
            page = browser.new_page()
            try:
                self._load_page(page, symbol)
                return page.content()
            finally:
                page.close()

    def fetch_pages(self, symbols: Iterable[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        with self._browser_session() as browser:
            for symbol in symbols:
                page = browser.new_page()
                try:
                    self._load_page(page, symbol)
                    result[symbol.upper()] = page.content()
                finally:
                    page.close()
        return result

    def fetch_constituent_pages(
        self,
        symbol: str,
        *,
        page_numbers: Iterable[int],
        page_size: int = 50,
    ) -> list[str]:
        html_pages: list[str] = []
        with self._browser_session() as browser:
            for page_number in page_numbers:
                page = browser.new_page()
                try:
                    self._load_page(page, symbol, page_number=page_number, page_size=page_size)
                    html_pages.append(page.content())
                finally:
                    page.close()
        return html_pages

    def _browser_session(self):
        try:
            from rustwright.sync_api import sync_playwright
        except ImportError as exc:
            raise OpenScreenerError(
                "rustwright is not installed. Install project dependencies before using the live scraper."
            ) from exc

        manager = sync_playwright().start()
        try:
            browser = manager.chromium.launch(headless=self.headless)
        except Exception as exc:
            manager.stop()
            raise OpenScreenerError(
                "Could not launch rustwright Chromium. Install browser binaries with "
                "`python -m rustwright install chromium`."
            ) from exc

        class _Session:
            def __enter__(self_inner):
                return browser

            def __exit__(self_inner, exc_type, exc, tb):
                browser.close()
                manager.stop()

        return _Session()

    def _load_page(self, page, symbol: str, *, page_number: int | None = None, page_size: int | None = None) -> None:
        url = self._build_url(symbol, page_number=page_number, page_size=page_size)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        except OpenScreenerError:
            raise
        except Exception as exc:
            raise OpenScreenerError(f"Could not load Screener page for symbol '{symbol.upper()}'.") from exc

        status = getattr(response, "status", None)
        if isinstance(status, int) and status >= 400:
            raise OpenScreenerError(f"Screener.in returned HTTP {status} for symbol '{symbol.upper()}'.")

        try:
            page.wait_for_selector("#top", timeout=self.timeout_ms)
        except Exception as exc:
            title = self._safe_page_title(page)
            detail = f" Page title: {title}." if title else ""
            raise OpenScreenerError(f"Could not find Screener page content for symbol '{symbol.upper()}'.{detail}") from exc

    def _safe_page_title(self, page) -> str:
        try:
            return str(page.title())
        except Exception:
            return ""

    def _build_url(self, symbol: str, *, page_number: int | None = None, page_size: int | None = None) -> str:
        path_suffix = "/consolidated/" if self.consolidated else "/"
        base_url = self.base_url.format(symbol=symbol.upper(), path_suffix=path_suffix)
        query: dict[str, int] = {}
        if page_number is not None:
            query["page"] = page_number
        if page_size is not None:
            query["limit"] = page_size
        if not query:
            return base_url
        return f"{base_url}?{urlencode(query)}"
