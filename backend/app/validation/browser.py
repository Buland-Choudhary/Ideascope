"""A single long-lived Chromium instance, shared across render checks
(docs/PLAN.md §5.2): "validation runs against a single long-lived Chromium
instance (fresh browser *context* per check, not fresh browser), guarded by
a semaphore (e.g. max 2-3 concurrent render checks)." Headless Chromium is
the backend's dominant memory consumer — this is what keeps a single-instance
deployment viable and doubles as backpressure under load.

The generation pipeline is currently fully synchronous (docs/PLAN.md §5.2,
Phase 3-4 scope — async/JIT delivery is Phase 6), so this uses Playwright's
sync API and a ``threading.Semaphore`` rather than asyncio — FastAPI runs sync
route handlers in a thread pool, so a thread-based semaphore achieves the same
cross-request concurrency cap.
"""

import contextlib
import os
import threading
from collections.abc import Iterator

from playwright.sync_api import Browser, Page, Playwright, ViewportSize, sync_playwright

# This CI/sandbox environment ships a preinstalled Chromium at a fixed path
# (faster than a fresh `playwright install` per session). A normal checkout —
# e.g. a developer's laptop — won't have this path; there, ``executable_path``
# is left as ``None`` so Playwright falls back to its own browser, installed
# via `playwright install chromium` (see backend/README.md).
_SANDBOX_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _chromium_executable_path() -> str | None:
    return _SANDBOX_CHROMIUM if os.path.exists(_SANDBOX_CHROMIUM) else None


_lock = threading.Lock()
_playwright_ctx: Playwright | None = None
_browser: Browser | None = None
_semaphore: threading.Semaphore | None = None


def _ensure_started(max_concurrent: int) -> Browser:
    global _playwright_ctx, _browser, _semaphore
    with _lock:
        if _browser is None:
            _playwright_ctx = sync_playwright().start()
            _browser = _playwright_ctx.chromium.launch(
                executable_path=_chromium_executable_path(),
                args=["--no-sandbox"],
            )
            _semaphore = threading.Semaphore(max_concurrent)
        return _browser


def shutdown() -> None:
    """Close the shared browser. Tests call this to avoid leaking processes."""
    global _playwright_ctx, _browser, _semaphore
    with _lock:
        if _browser is not None:
            _browser.close()
            _browser = None
        if _playwright_ctx is not None:
            _playwright_ctx.stop()
            _playwright_ctx = None
        _semaphore = None


@contextlib.contextmanager
def get_page(max_concurrent: int = 3, *, viewport: ViewportSize | None = None) -> Iterator[Page]:
    """A fresh, isolated page for one render check, under the concurrency cap."""
    browser = _ensure_started(max_concurrent)
    assert _semaphore is not None
    with _semaphore:
        context = browser.new_context(viewport=viewport or ViewportSize(width=800, height=500))
        try:
            page = context.new_page()
            yield page
        finally:
            context.close()
