"""Ready-to-run verification: does the stack pass a live bot check?

Launches Camoufox (headed under Xvfb, Windows profile, geoip coherence),
loads https://deviceandbrowserinfo.com/are_you_a_bot, and prints the verdict.

Run:  xvfb-run -a -s "-screen 0 1366x900x24" python3 human_test.py
Expected: VERDICT: '✅ You are human!'  |  TRUE FLAGS: []
"""
import asyncio, json, random, sys, time

import pyautogui
pyautogui.PAUSE = 0  # trap #3: default 0.1s x hundreds of cursor points = minutes per move

from humancursor.system_cursor import SystemCursor  # trap: NOT humancursor.system


def human_click(page, rect):
    """Click a page element with the real OS cursor via mozInnerScreen coords."""
    geo = page.evaluate(
        "({mx: window.mozInnerScreenX, my: window.mozInnerScreenY, dpr: window.devicePixelRatio})"
    )
    x = geo["mx"] + (rect["x"] + rect["width"] * random.uniform(0.3, 0.7)) * geo["dpr"]
    y = geo["my"] + (rect["y"] + rect["height"] * 0.6) * geo["dpr"]
    sc = SystemCursor()
    sc.move_to((int(x), int(y)))                    # bezier human curve
    page.wait_for_timeout(random.randint(150, 400))
    sc.click_on((int(x), int(y)))
    return (x, y)


def wander(n=8, w=1100, h=700):
    sc = SystemCursor()
    for _ in range(n):
        sc.move_to((random.randint(100, w), random.randint(100, h)))
        time.sleep(random.uniform(0.3, 0.9))


async def main():
    from camoufox.async_api import AsyncCamoufox

    # The winning config: headed + OS profile + geoip. No humanize (trap #1).
    async with AsyncCamoufox(headless=False, os="windows", geoip=True) as b:
        page = await b.new_page(viewport={"width": 1200, "height": 800})
        # trap #2: no #anchor in the URL — some anchor-routes hang forever
        await page.goto("https://deviceandbrowserinfo.com/are_you_a_bot",
                        timeout=60000, wait_until="domcontentloaded")

        wander()  # behavioral warm-up

        # --- example: human-typed form interaction on the interactions page ---
        # await page.goto("https://deviceandbrowserinfo.com/are_you_a_bot_interactions", ...)
        # email = await page.evaluate("(() => { const e=document.getElementById('email'); const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()")
        # human_click(page, email)
        # await page.keyboard.type("jean.dupont@mail.fr", delay=random.randint(60, 160))

        # read the verdict (appears once the fingerprint POST returns)
        verdict, flags = "", []
        for _ in range(30):
            await page.wait_for_timeout(1000)
            verdict = await page.evaluate(
                "(() => { const e=document.getElementById('resultsBotTest'); return e ? e.innerText.trim() : ''; })()"
            )
            if verdict:
                break
        js = await page.evaluate(
            "(() => { const e=document.getElementById('jsonResult'); return e ? e.innerText : ''; })()"
        )
        try:
            flags = [k for k, v in json.loads(js).get("details", {}).items() if v is True]
        except Exception:
            pass
        print("VERDICT:", repr(verdict))
        print("TRUE FLAGS:", flags)
        await page.screenshot(path="human_test.png")


asyncio.run(main())
