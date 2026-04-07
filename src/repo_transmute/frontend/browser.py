"""Browser automation utilities for RepoTransmute using Playwright.

This module is optional — requires `playwright` and `pillow` packages.
Install with: pip install playwright pillow && playwright install chromium
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List

import asyncio


if TYPE_CHECKING:
    from playwright.async_api import Browser


# Optional imports - these packages must be installed separately
try:
    from playwright.async_api import async_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _check_playwright() -> None:
    """Raise ImportError if playwright is not installed."""
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError(
            "playwright is not installed. Install with:\n"
            "  pip install playwright pillow\n"
            "  playwright install chromium"
        )


def _check_pillow() -> None:
    """Raise ImportError if pillow is not installed."""
    if not PIL_AVAILABLE:
        raise ImportError("pillow is not installed. Install with: pip install pillow")


async def _capture_screenshot_async(url: str, output: Path) -> None:
    """Async implementation of screenshot capture."""
    from playwright.async_api import async_playwright
    _check_playwright()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        await page.screenshot(path=str(output))
        await browser.close()


def capture_screenshot(url: str, output: Path) -> None:
    """Capture screenshot of a URL using Playwright.
    
    Args:
        url: The URL to capture.
        output: Path to save the screenshot.
    
    Raises:
        ImportError: If playwright is not installed.
    """
    _check_playwright()
    asyncio.run(_capture_screenshot_async(url, output))


def compare_screenshots(original: Path, generated: Path) -> float:
    """Compare two screenshots, return similarity score 0-1.
    
    Uses pixel-by-pixel comparison with PIL.
    
    Args:
        original: Path to the original screenshot.
        generated: Path to the generated screenshot.
        
    Returns:
        Similarity score between 0 (completely different) and 1 (identical).
    
    Raises:
        ImportError: If pillow is not installed.
    """
    _check_pillow()
    
    img1 = Image.open(original).convert("RGB")
    img2 = Image.open(generated).convert("RGB")
    
    # Resize to match if different sizes
    if img1.size != img2.size:
        img2 = img2.resize(img1.size)
    
    # Simple pixel comparison
    pixels1 = list(img1.getdata())
    pixels2 = list(img2.getdata())
    
    if len(pixels1) != len(pixels2):
        return 0.0
    
    diff_count = sum(1 for p1, p2 in zip(pixels1, pixels2) if p1 != p2)
    total_pixels = len(pixels1)
    
    return 1.0 - (diff_count / total_pixels)


class BrowserValidator:
    """Browser-based validation for rendered pages.
    
    Requires playwright to be installed.
    """
    
    def __init__(self):
        _check_playwright()
        self._browser = None
        self._playwright = None
    
    async def _ensure_browser(self):
        """Lazy initialization of browser."""
        from playwright.async_api import async_playwright
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch()
        return self._browser
    
    async def _close_async(self):
        """Close the browser instance."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
    
    def close(self):
        """Close the browser instance."""
        try:
            asyncio.run(self._close_async())
        except RuntimeError:
            # Already running - just ignore
            pass
    
    async def close_async(self):
        """Close the browser instance asynchronously."""
        await self._close_async()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    async def _validate_page_loads_async(self, url: str) -> bool:
        """Async implementation of page load validation."""
        from playwright.async_api import Error as PlaywrightError
        browser = None
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()
            response = await page.goto(url, wait_until="domcontentloaded")
            await page.close()
            return response is not None and response.ok
        except PlaywrightError:
            return False
    
    def validate_page_loads(self, url: str) -> bool:
        """Check if a page loads successfully.
        
        Args:
            url: The URL to validate.
            
        Returns:
            True if page loads without errors.
        """
        return asyncio.run(self._validate_page_loads_async(url))
    
    async def _check_console_errors_async(self, url: str) -> List[str]:
        """Async implementation of console error checking."""
        from playwright.async_api import Error as PlaywrightError
        errors: List[str] = []
        browser = None
        
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()
            
            def handle_console(msg):
                if msg.type == "error":
                    errors.append(msg.text)
            
            page.on("console", handle_console)
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1)
            await page.close()
        except PlaywrightError:
            errors.append("Failed to load page")
        
        return errors
    
    def check_console_errors(self, url: str) -> List[str]:
        """Check for console errors on a page.
        
        Args:
            url: The URL to check.
            
        Returns:
            List of console error messages.
        """
        return asyncio.run(self._check_console_errors_async(url))
    
    async def _get_render_time_async(self, url: str) -> float:
        """Async implementation of render time measurement."""
        from playwright.async_api import Error as PlaywrightError
        browser = None
        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()
            
            start_time = asyncio.get_event_loop().time()
            await page.goto(url, wait_until="networkidle")
            end_time = asyncio.get_event_loop().time()
            
            await page.close()
            return end_time - start_time
        except PlaywrightError:
            return -1.0
    
    def get_render_time(self, url: str) -> float:
        """Measure page render time in seconds.
        
        Args:
            url: The URL to measure.
            
        Returns:
            Render time in seconds.
        """
        return asyncio.run(self._get_render_time_async(url))