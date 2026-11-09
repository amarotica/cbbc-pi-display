"""Real Chromium tests, using a local HTTP server (no public network required)."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import unittest

from signage.renderer import render


class Pages(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/404":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/good")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        pages = {
            "/good": '<main id="menu" style="background:#164456;color:white;height:1600px"><h1>Menu $10</h1></main>',
            "/broken": '<main id="menu"><h1>Menu</h1><img src="/404"></main>',
            "/background": '<main id="menu" style="background-image:url(/404)">Menu</main>',
            "/unstable": '<main id="menu">Menu</main><script>let i=0;setInterval(()=>document.querySelector("main").textContent="Menu "+i++,20)</script>',
            "/empty": '<main id="menu"></main>',
            "/soft-error": '<main>Maintenance</main>',
            "/viewport": '''<style>html,body{margin:0;background:#0b3c4a}h1{margin:0}#menu{width:100vw;height:100vh;background:#e79b46}</style>
                <main id="menu"><h1>Menu</h1><span id="size"></span></main>
                <script>document.querySelector('#size').textContent=window.innerWidth+'x'+window.innerHeight;
                if(innerWidth!==1080 || innerHeight!==1920 || devicePixelRatio!==1)
                    document.querySelector('#menu').style.background='#ff00ff';</script>''',
            "/offset": '<style>body{margin:0;background:#0b3c4a}#menu{margin-top:900px;height:100px;background:#e79b46}</style><main id="menu">Menu</main>',
        }
        self.wfile.write(pages.get(self.path, "missing").encode())

    def log_message(self, *args):
        pass


class RendererTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Pages)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        options = {"headless": True, "chromium_sandbox": True}
        if os.environ.get("SIGNAGE_TEST_BROWSER"):
            options["executable_path"] = os.environ["SIGNAGE_TEST_BROWSER"]
        self.browser = await self.playwright.chromium.launch(**options)
        self.config = {"timeout_seconds": 3, "settle_seconds": 0.1, "stable_seconds": 0.2, "timezone": "America/Los_Angeles"}

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def capture(self, path, viewport=None, **options):
        channel = {"url": f"http://127.0.0.1:{self.server.server_port}{path}", "ready_selector": "#menu", "capture_selector": "#menu", **options}
        return await render(self.browser, channel, self.config, viewport or {"width": 800, "height": 600})

    async def test_tall_document_does_not_change_the_capture_dimensions(self):
        import io
        from PIL import Image
        result = await self.capture("/good")
        self.assertEqual(Image.open(io.BytesIO(result)).size, (800, 600))

    async def test_portrait_capture_matches_the_true_1080_by_1920_viewport(self):
        import io
        from PIL import Image
        result = await self.capture("/viewport", viewport={"width": 1080, "height": 1920})
        image = Image.open(io.BytesIO(result)).convert("RGB")
        self.assertEqual(image.size, (1080, 1920))
        # Website background reaches all four edges; there is no fitted page box.
        for corner in ((0, 0), (1079, 0), (0, 1919), (1079, 1919)):
            self.assertEqual(image.getpixel(corner), (231, 155, 70))

    async def test_validation_selector_does_not_scroll_the_viewport_to_that_element(self):
        import io
        from PIL import Image
        result = await self.capture("/offset")
        image = Image.open(io.BytesIO(result)).convert("RGB")
        self.assertEqual(image.getpixel((400, 300)), (11, 60, 74))

    async def test_invalid_pages_are_rejected(self):
        for path in ("/404", "/redirect", "/broken", "/background", "/unstable", "/empty", "/soft-error"):
            with self.subTest(path=path), self.assertRaises(Exception):
                await self.capture(path)

    async def test_required_text_rejects_wrong_content(self):
        with self.assertRaises(ValueError):
            await self.capture("/good", required_text="FOOD SPECIALS")


if __name__ == "__main__":
    unittest.main()
