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

## Camoufox ships uBlock Origin — it silently breaks ad chains

Camoufox bundles uBlock Origin and installs it into every profile
(`DefaultAddons.UBO`). Ad/anti-fraud domains on EasyList (e.g. `c.adsco.re`)
get cancelled **pre-network** (`NS_ERROR_ABORT`, no TCP connection at all),
while non-listed domains load fine — very confusing to debug.

Symptoms: anti-fraud script never loads; the page's ad engine reports a
timeout code instead of a signature; `page.on("requestfailed")` shows
`NS_ERROR_ABORT` for the ad domain only.

Confirm it: watch the browser fetch `easylist-downloads.adblockplus.org` /
`filters.adtidy.org` (visible in a proxy log), or check
`profile/prefs.js` for `uBlock0@raymondhill.net`.

Fix: `exclude_addons=[DefaultAddons.UBO]` on the launch call.
**`addons=[]` is NOT enough** — it only controls *custom* addons, the bundled
UBO is still installed. A fresh temp profile does not help either: the lists
ship/refresh every run.

## Ad / popunder chains (AdScore-style)

| Symptom | Cause | Fix |
|---|---|---|
| Inventory request carries a tiny signature (`=3`) instead of a token | AdScore script (`c.adsco.re`, ~100 KB + Web Workers) never finished loading — slow proxy, blocked, or the click fired before it was ready | Wait for a real signature before clicking: detect it in the inventory URL (see below), poll, then click |
| Signature detector never fires although signatures exist | the query-string parameter holding the signature is **obfuscated and CHANGES on every engine load** (`kcevJWRx=...` one load, `jiLzBxnR=...` the next) | Never hardcode the param name — scan all query params for a value > 50 chars (AdScore tokens start with `BQOC`) |
| Popunder opens `about:blank` and stays empty | the mechanism worked (`window.open('about:blank')` then set location) but the inventory answered "no campaign" | Check the inventory **response body**: `window.<rand>.parse({"result":0,"url":""})` = server has nothing to serve — this is a server-side decision (geo targeting / IP history / account has no campaigns), not a detection failure |
| Popup detection always "true", retry loop exits immediately | Camoufox contexts keep an initial `about:blank` page, so `len(ctx.pages) > 1` is always true | Filter: `[p for p in ctx.pages if not p.url.startswith(("about:blank", "data:"))]` |
| Clicks on the ad iframe open fallback pages (aads.com, maads.com, dexranger.com…) | a-ads banner fallback house-ads, unrelated to the popunder chain | Don't confuse them with the popunder; click the page body instead if you only want the popunder |
| Clicks rejected / no reaction | popunder engines require `isTrusted` clicks and reject right-clicks | Real X11 mouse events (HumanCursor / pyautogui), left-click only |

Diagnostics that pin down each stage: log every request/response URL (the
signature travels in the inventory URL), and capture the inventory **response
body** — `window.<rand>.parse({"result":N,"url":"..."})` is the ad network's
actual decision. Dump results incrementally (`json.dump` after each phase) or
a killed run leaves nothing behind.

## Proxies: what each failure mode looks like

| Pattern | Diagnosis |
|---|---|
| curl/python through the proxy fetches every host; **Firefox hangs or aborts pre-network on ad-domain SNIs only** | TLS-fingerprint (JA3) filtering on the proxy path: OpenSSL clients pass, NSS (Firefox) handshakes to ad SNIs are killed. Test with a local MITM re-encryption (mitmproxy upstream mode) — if Firefox then rejects the MITM cert, you need a real CA trust setup (certutil into the NSS DB); often simpler to change provider |
| Browser can't use the proxy at all: "Browser does not support socks5 proxy authentication" | Playwright/Firefox has no SOCKS5 auth — write a tiny local HTTP→SOCKS5 asyncio bridge (CONNECT relay) and point the browser at `127.0.0.1` |
| Free "residential" proxies from public lists all die within minutes and are all datacenter | Public HTTP lists are scraped open proxies (Oracle/Alibaba/OVH…). For real residential ISPs use `monosans/proxy-list` **proxies.json** (has ASN + ISP metadata — filter for telecom names), then verify with ip-api (`hosting:false` is the stable signal; the `proxy` boolean is volatile — an ISP retail line flips between runs) |
| Proxy works for curl, dies under the browser's parallel load | Free proxies choke on bursts. Route **only the ad domains** through the proxy and load the rest direct (a local per-host CONNECT router): the page host's IP is irrelevant to the ad decision — only the IP that touches the ad network matters. Add per-upstream timeouts and a failover pool |
| Everything worked in earlier runs but ad domains now abort pre-network | A **persistent profile** accumulates state fresh profiles lack (downloaded tracking blocklists, certs) — behavior changes over time. Compare against a fresh temp profile before blaming the proxy |

## Resource-constrained boxes (2 GB RAM / cgroup limits)

- `dmesg | grep -i oom` first — "Target page, context or browser has been
  closed" mid-run is often the OOM killer, not a proxy problem.
- `/tmp` is often a **tmpfs**: accumulated logs/screenshots count as
  un-reclaimable memory. `du -sh /tmp/*` — an 800 MB leftover log file cost us
  the whole browser budget.
- Cut Firefox RAM: `"dom.ipc.processCount": 1`,
  `"browser.cache.disk.enable": False`, `"browser.cache.memory.capacity": 16384`.
- One persistent `Xvfb :99` + `DISPLAY=:99` instead of `xvfb-run` per run —
  xvfb-run leaves orphan Xvfb processes (~75 MB each).
- `pkill -f <pattern>` matches **your own shell's command line** when the
  pattern appears in the block you're running — the block kills itself
  (exit 143/137). Use `pkill -x <name>` or kill by PID.

## WebRTC leaks the real IP under proxies (fixed in config)

CreepJS/pixelscan-style sites read the STUN `srflx` candidate: even with a
perfect fingerprint, the browser hands out the **real public IP** — fatal when
the whole point is a proxy IP. Baseline test showed `candidate:... typ srflx
raddr 0.0.0.0` carrying the host IP straight into the fingerprint.

Fix (in `firefox_user_prefs`):
```
"media.peerconnection.enabled": False,
"media.peerconnection.ice.default_address_only": True,
"media.peerconnection.ice.no_host": True,
```
Result: CreepJS reports WebRTC `blocked` instead of the real IP. Cost: sites
note WebRTC as disabled — far cheaper than an IP incoherence.

## Known limits of the stack

- Camoufox OS profiles: only `macos`, `windows`, `linux` — no Android/iOS.
- Camoufox's canvas readback noise (RFP-style) triggers one weak-signal flag
  on deviceandbrowserinfo.com **unless geoip coherence is on**; with geoip on,
  zero flags.
- GPU note: under Xvfb headed, WebGL is software-rendered but coherent with
  the spoofed OS profile (e.g. "Apple M1, or similar" for macos) — never
  combine `os="macos"` with a Windows-looking WebGL string.
- Ad networks answer `result:0` (no campaign) identically for "verdict: bot"
  and "no campaign for your geo" — the AdScore signature is opaque to the
  client, so only a comparative test (your own clean IP vs the test IP)
  separates detection from plain inventory emptiness.
