"""Render fresh pages out of sight; never expose a browser error to the displays."""
import asyncio
from urllib.parse import urlsplit

from signage.common import pixel_hash

# Validate images in the configured readiness region, including lazy images
# and CSS backgrounds, before publishing a snapshot of the viewport.
VALIDATE_MEDIA = r"""async (selector) => {
    await document.fonts.ready;
    if ([...document.fonts].some(font => font.status === 'error'))
        throw new Error('A font failed to load');
    const root = selector ? document.querySelector(selector) : document.body;
    if (!root) throw new Error('Capture region is absent');
    const nodes = [root, ...root.querySelectorAll('*')];
    const images = nodes.filter(node => node.tagName === 'IMG');
    for (const image of images) {
        image.loading = 'eager';
        await image.decode();
        if (!image.naturalWidth) throw new Error('An image is empty');
    }
    const urls = new Set();
    for (const node of nodes) {
        for (const pseudo of [null, '::before', '::after']) {
            const background = getComputedStyle(node, pseudo).backgroundImage;
            for (const match of background.matchAll(/url\(["']?([^"')]+)["']?\)/g))
                urls.add(match[1]);
        }
    }
    await Promise.all([...urls].map(async url => {
        const image = new Image(); image.src = url; await image.decode();
    }));
    if (!root.innerText.trim() && !images.length && !urls.size && !root.querySelector('svg,canvas'))
        throw new Error('Capture region is empty');
    if (root.querySelector('iframe,video'))
        throw new Error('Static signage does not support iframe/video content');
}"""


def same_destination(requested, actual):
    def identity(url):
        parsed = urlsplit(url)
        return parsed.hostname, parsed.path.rstrip("/")
    return identity(requested) == identity(actual)


async def render(browser, channel, config, viewport):
    """A fresh context avoids stale HTTP caches, cookies and service workers."""
    timeout = config["timeout_seconds"]
    async with asyncio.timeout(timeout):
        context = await browser.new_context(
            viewport=viewport, device_scale_factor=1, locale="en-US",
            timezone_id=config["timezone"], reduced_motion="reduce", service_workers="block",
        )
        try:
            page = await context.new_page()
            # Disable Chromium's cache without adding cross-origin request headers:
            # global Cache-Control/Pragma headers break CORS on Google-hosted fonts.
            cdp = await context.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
            page.set_default_timeout(timeout * 1000)
            failures = set()
            critical = {"document", "stylesheet", "font", "image"}

            def failed(request):
                if request.resource_type in critical:
                    failures.add(request.url)

            def response_received(response):
                if response.status >= 400 and response.request.resource_type in critical:
                    failures.add(response.url)

            page.on("requestfailed", failed)
            page.on("response", response_received)
            response = await page.goto(channel["url"], wait_until="load")
            if response is None or not 200 <= response.status < 300:
                raise ValueError(f"HTTP {response.status if response else 'no response'}")
            if not same_destination(channel["url"], page.url):
                raise ValueError(f"Unexpected redirect to {page.url}")
            await page.locator(channel["ready_selector"]).first.wait_for(state="visible")
            selector = channel.get("capture_selector")
            await page.add_style_tag(content="html {scrollbar-width:none} * {caret-color:transparent!important}")
            # Promote native lazy images before waiting for layout to settle.
            await page.locator("img").evaluate_all("images => images.forEach(i => i.loading = 'eager')")
            await asyncio.sleep(config["settle_seconds"])

            async def capture():
                await page.evaluate(VALIDATE_MEDIA, selector)
                required = channel.get("required_text", "")
                if required and required not in await page.locator(selector or "body").inner_text():
                    raise ValueError("Required menu text is absent")
                # A TV is one browser viewport. Capturing a tall element/document
                # and fitting it afterward shrinks the website and adds bars.
                # The website owns fitting its header and media into this box.
                await page.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})")
                png = await page.screenshot(type="png", full_page=False, animations="disabled", caret="hide")
                if failures:
                    raise ValueError(f"Failed page assets: {sorted(failures)[:3]}")
                return png

            first = await capture()
            await asyncio.sleep(config["stable_seconds"])
            second = await capture()
            if pixel_hash(first) != pixel_hash(second):
                raise ValueError("Page is still changing; retaining previous menu")
            return second
        finally:
            await context.close()
