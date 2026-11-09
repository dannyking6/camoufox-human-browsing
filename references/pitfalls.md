# Pitfalls reference — every rule in SKILL.md traced to a real failure

Each item below was reproduced, diagnosed and fixed during live testing
against bot-detection sites (antcpt.com, antybrowser.com, pixelscan.net,
creepjs, bot.incolumitas.com, deviceandbrowserinfo.com).

## Camoufox launch

| Symptom | Cause | Fix |
|---|---|---|
| `AsyncCamoufox(...)` never returns, no error, when `headless=False` | `humanize=True` in headed mode blocks inside launch | Drop `humanize`; use HumanCursor for mouse |
| `goto("https://site/#anchor")` hangs forever | anchor-routed SPA waits on a backend that is down/slow | goto the plain URL; set hash afterwards via `evaluate` if needed |
| Headless works but every bot site flags you | headless Firefox exposes **zero** WebGL renderers — fatal incoherence | Always `headless=False` under Xvfb |
| Verdict "bot" although every signal is false | timezone/locale not aligned with exit IP | `geoip=True` (this single flag flipped deviceandbrowserinfo.com from "You are a bot!" to "You are human!") |

## Mouse / coordinates

| Symptom | Cause | Fix |
|---|---|---|
| Clicks miss fields; inputs stay empty; no error | Firefox under Xvfb reports `outerHeight < innerHeight` (e.g. 720 vs 800) → the classic `screenY + (outerH-innerH)` offset is **negative** | Compute screen coords with `window.mozInnerScreenX/Y` (+ `devicePixelRatio`) |
| One cursor move takes minutes | `pyautogui.PAUSE` defaults to 0.1 s, applied after every moveTo of the trajectory (hundreds of points) | `pyautogui.PAUSE = 0` before cursor-lib work |
| human-mouse (sarperavci) move takes ~3.6 h for 1200 px | per-step delay = `distance^1.75 ms`, trajectory interpolated to ~1366 points | Monkeypatch `human_mouse.mouse.create_delay` (name imported into `mouse.py`'s namespace — patching `utils` is a no-op) with `min(i*0.001, 0.002)`; or just use HumanCursor which needs nothing |
| `ModuleNotFoundError: humancursor.system` | wrong submodule path | `from humancursor.system_cursor import SystemCursor` |
| Pip package shadowed by an old local file with the same name | script dir is `sys.path[0]` | Rename the local file |

## Automation-framework leaks (why Camoufox, not Chromium)

| Tool | pixelscan | creepjs | verdict |
|---|---|---|---|
| Playwright Chromium vanilla | bot | 94% | unusable |
| nodriver (hardened: webdriver undefined, CDP UA-CH override) | Human | **50%** — UA leaks through Web Workers, CDP cannot fix it | partial |
| **Camoufox headed + os + geoip** | **Human/Clear** | **6%** | **winner** |

reCAPTCHA v3 scores: headless 0.3 → headed 0.9 (Xvfb); antybrowser: Camoufox
0.7 "Human", nodriver headed 0.9, nodriver headless 0.3. Headed mode is the
dominant factor for Google's scoring.

## Cloudflare Turnstile (unsolved by fingerprinting — by design)

Symptom: `iframe[src*="challenges.cloudflare.com"]` is never created, on any
tool (Camoufox/nodriver/vanilla Chromium), any input method (CDP or real X11
mouse), headless or headed, and on 4 different IPs (datacenter direct, NL
datacenter socks5, "residential" MX, residential PH PLDT).

Proof that the local stack is fine: the auto-pass test key
`1x00000000000000000000AA` yields a token in Camoufox, and antybrowser's own
local-signal panel shows "No obvious red flags". The interactive challenge is
gated **server-side** (IP reputation + TLS + cookie history) before any page
JS runs. Free proxies from GitHub lists — even with `proxy:false` in ip-api —
are known to Cloudflare. Solutions: paid dedicated residential IP, a captcha
service (CapSolver/2Captcha), or an IP with existing `cf_clearance` history.

## Xvfb / X11 environment

- Firefox may fail with "Authorization required" even when `xdpyinfo` works:
  export the `XAUTHORITY` of the *running* Xvfb:
  `ps auxww | grep Xvfb` → `-auth /tmp/xvfb-run.XXXX/Xauthority`.
- Long-lived background launches need `setsid nohup ... < /dev/null &` — plain
  `nohup ... &` can die with the tool session.
- Screenshot the whole virtual screen for verification:
  `DISPLAY=:99 import -window root shot.png` (imagemagick).
- Firefox profile errors ("profile cannot be loaded"): `rm -rf` the profile
  dir and recreate it empty before launch.

## Known limits of the stack

- Camoufox OS profiles: only `macos`, `windows`, `linux` — no Android/iOS.
- Camoufox's canvas readback noise (RFP-style) triggers one weak-signal flag
  on deviceandbrowserinfo.com **unless geoip coherence is on**; with geoip on,
  zero flags.
- GPU note: under Xvfb headed, WebGL is software-rendered but coherent with
  the spoofed OS profile (e.g. "Apple M1, or similar" for macos) — never
  combine `os="macos"` with a Windows-looking WebGL string.
