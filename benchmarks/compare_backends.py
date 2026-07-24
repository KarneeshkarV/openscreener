"""Compare end-to-end browser session overhead for Playwright and Rustwright."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version


HTML = b"<!doctype html><html><body><main id='top'>benchmark</main></body></html>"


class BenchmarkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, format: str, *args: object) -> None:
        pass


def sync_playwright_for(backend: str):
    if backend == "rustwright":
        from rustwright.sync_api import sync_playwright
    else:
        from playwright.sync_api import sync_playwright
    return sync_playwright


def run_once(sync_playwright, url: str) -> float:
    started = time.perf_counter()
    manager = sync_playwright().start()
    browser = manager.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("#top", timeout=30_000)
        page.content()
    finally:
        page.close()
        browser.close()
        manager.stop()
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=("playwright", "rustwright"))
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", 0), BenchmarkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    sync_playwright = sync_playwright_for(args.backend)

    try:
        for _ in range(args.warmups):
            run_once(sync_playwright, url)
        samples = [run_once(sync_playwright, url) for _ in range(args.runs)]
    finally:
        server.shutdown()
        server.server_close()

    print(
        json.dumps(
            {
                "backend": args.backend,
                "package_version": version(args.backend),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "runs": args.runs,
                "warmups": args.warmups,
                "median_ms": round(statistics.median(samples) * 1000, 2),
                "mean_ms": round(statistics.mean(samples) * 1000, 2),
                "stdev_ms": round(statistics.stdev(samples) * 1000, 2),
                "min_ms": round(min(samples) * 1000, 2),
                "max_ms": round(max(samples) * 1000, 2),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
