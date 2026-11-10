---
name: camoufox-human-browsing
description: "Set up a fully working, battle-tested undetectable browsing stack in minutes: Camoufox (anti-detect Firefox) running HEADED under Xvfb with geoip coherence, driven by a REAL human-like OS cursor (HumanCursor) and human typing cadence — verified against live bot-detection sites (deviceandbrowserinfo.com verdict 'You are human!' with zero flags, pixelscan Human, creepjs 6% headless). Use when the user wants to automate a browser without being detected as a bot, needs a Camoufox setup that passes bot checks, wants human-like mouse movement and typing in automation, or asks how to install/integrate Camoufox + HumanCursor."
version: 1.0.0
tags: [camoufox, anti-detection, bot-detection, human-cursor, browser-automation, fingerprint, playwright, undetectable]
---

# Camoufox + HumanCursor: undetectable human browsing stack

A proven configuration (validated live: "You are human!" with **zero flags**
on deviceandbrowserinfo.com, Human/Clear on pixelscan, 6% headless on creepjs,
0.7–0.9 on reCAPTCHA v3). Follow this exactly — every rule below exists
because breaking it caused a real, diagnosed failure.

## 1. Install (one-time)

```bash
pip install "camoufox[geoip]" --break-system-packages   # Debian/Ubuntu/Kali
python3 -m camoufox fetch                                # downloads the patched Firefox (~150 MB)
pip install git+https://github.com/riflosnake/HumanCursor --break-system-packages
apt-get install -y xvfb imagemagick                      # virtual display + screenshots
```

- HumanCursor import is `from humancursor.system_cursor import SystemCursor`
  (NOT `humancursor.system` — it fails).
- If `camoufox` install conflicts, add `--ignore-installed wcwidth`.

## 2. Launch — the winning config

Always run under a virtual display (never headless):

```bash
xvfb-run -a -s "-screen 0 1366x900x24" python3 your_script.py
```

```python
import asyncio
from camoufox.async_api import AsyncCamoufox
from camoufox.addons import DefaultAddons

async def main():
    async with AsyncCamoufox(headless=False, os="windows", geoip=True,
                             exclude_addons=[DefaultAddons.UBO]) as b:
        page = await b.new_page(viewport={"width": 1200, "height": 800})
        await page.goto("https://example.com", timeout=60000, wait_until="domcontentloaded")
        # ... human interaction (section 3) ...
asyncio.run(main())
```

The three flags are non-negotiable:

| Flag | Why it must be there | Failure if missing |
|---|---|---|
| `headless=False` (+ Xvfb) | Headless Firefox exposes **no WebGL at all** — a fatal incoherence; it also drops reCAPTCHA v3 from 0.9 to 0.3 | Instant bot verdicts |
| `os="windows"` (or `"macos"`) | Coherent OS fingerprint (platform, oscpu, fonts, GPU). Valid values: only `macos`, `windows`, `linux` — no mobile | Datacenter-looking Linux |
| `geoip=True` | Aligns timezone + locale with the exit IP. **This was the single missing flag that flipped a "You are a bot!" verdict into "You are human!" with zero flags** | Timezone/locale-vs-IP weak signal → bot |

Do NOT add `humanize=True` in headed mode — it **hangs the launch** (infinite
block inside `AsyncCamoufox.__aenter__`). HumanCursor replaces it.

Also add `exclude_addons=[DefaultAddons.UBO]` whenever the automation touches
**ad or anti-fraud domains** (adsco.re, ad networks, trackers): Camoufox
silently bundles uBlock Origin and it cancels those requests pre-network
(`NS_ERROR_ABORT`, no connection attempt), which looks exactly like a proxy or
server failure. For plain bot-check sites it is harmless; for anything
ad-related it is fatal. Details in `references/pitfalls.md`.

## 3. Human interaction (real OS cursor + typing cadence)

HumanCursor moves the **real X11 cursor**, so the page sees genuine OS-level
`mousemove` events with coherent `screenX/screenY`:

```python
import random, pyautogui
from humancursor.system_cursor import SystemCursor

pyautogui.PAUSE = 0  # critical: default 0.1s per call x hundreds of points = minutes per move

def click_element(page, el_rect):
    geo = page.evaluate("({mx: window.mozInnerScreenX, my: window.mozInnerScreenY, dpr: window.devicePixelRatio})")
    x = geo["mx"] + (el_rect["x"] + el_rect["width"]  * random.uniform(0.3, 0.7)) * geo["dpr"]
    y = geo["my"] + (el_rect["y"] + el_rect["height"] * 0.6) * geo["dpr"]
    sc = SystemCursor()
    sc.move_to((int(x), int(y)))          # bezier human curve, 0.5–2 s
    page.wait_for_timeout(random.randint(150, 400))
    sc.click_on((int(x), int(y)))         # moves + clicks at OS level

# typing: human cadence (typing-speed heuristics flag >200ms-constant or <50ms bursts)
page.keyboard.type("jean.dupont@mail.fr", delay=random.randint(60, 160))
```

### Coordinate calibration — the Firefox trap

Screen position of a page element = `mozInnerScreenX/Y` + rect (+ dpr).
**Never** use `screenX + (outerHeight - innerHeight)`: Firefox under Xvfb
reports `outerHeight < innerHeight` (e.g. 720 < 800), which silently shifts
every click 80px off-target (fields stay empty, no error raised).

```python
# warm-up: wander the cursor over the page before any interaction
for _ in range(8):
    sc.move_to((random.randint(100, 1100), random.randint(100, 700)))
    time.sleep(random.uniform(0.3, 0.9))
```

## 4. Verify the setup (2 minutes)

```bash
xvfb-run -a -s "-screen 0 1366x900x24" python3 scripts/human_test.py
```

Reads the verdict from `#resultsBotTest` on
`https://deviceandbrowserinfo.com/are_you_a_bot` (fast, no interaction needed:
"✅ You are human!" + zero true flags = stack works). Deeper behavioral check:
`/are_you_a_bot_interactions` (login form analyzes mouse + typing). Also good:
bot.sannysoft.com, creepjs (want <20% trust-murder), pixelscan.net (Human/Clear).

## 5. Pitfalls that cost us hours — do not rediscover them

1. **`humanize=True` + headed = launch hangs forever.** Remove it.
2. **`page.goto(url#someAnchor)` can hang indefinitely** on sites whose
   anchor-routes wait for a backend. Use the plain URL.
3. **`pyautogui.PAUSE` default (0.1s)** turns one human-cursor move into
   minutes. Set to 0 before any cursor lib work.
4. **human-mouse (sarperavci) is broken by design**: its per-step delay is
   `distance^1.75 ms` over ~1366 interpolated points → hours per move. If you
   must use it: monkeypatch `human_mouse.mouse.create_delay` (the name is
   imported INTO `mouse.py`'s namespace — patching `utils` does nothing) with
   a ~2 ms cap, plus `pyautogui.PAUSE = 0`. HumanCursor needs none of this.
5. **Import shadowing**: a local file named like an installed package (e.g.
   your own old `human_mouse.py`) silently wins over the pip package when the
   script's directory is on `sys.path`. Rename yours.
6. **nodriver/CDP leaks**: CDP-driven Chromium leaks the UA through Web Workers
   (creepjs 50%) and flags pixelscan. Camoufox (Firefox) does not — prefer it.
7. **Turnstile/reCAPTCHA on datacenter IPs**: if the challenge iframe is never
   served at all, it is IP reputation (server-side, pre-JS), not your
   fingerprint. Free "residential" proxies from GitHub lists are known to
   Cloudflare even when ip-api shows `proxy:false`. Test with the auto-pass
   key `1x00000000000000000000AA` to prove your flow, then get a clean IP.
8. **Xvfb + xauth**: if X clients fail with "Authorization required", find the
   `Xauthority` file of the running Xvfb (`ps auxww | grep Xvfb` → `-auth
   /tmp/xvfb-run.XXXX/Xauthority`) and export it as `XAUTHORITY`.

## 6. Files

- `scripts/setup.sh` — full install (idempotent).
- `scripts/human_test.py` — ready-to-run verdict test with the exact
  config, calibration and typing pattern.
- `references/pitfalls.md` — the full failure log behind each rule above.
