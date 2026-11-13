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
- The PopAds-style engine's inventory JSONP path is **random per load**
  (`displayvertising.com/awwdvomzzvxhbepzdqs?...`), not a fixed `/c` — capture
  with `"displayvertising" in url and "?" in url`, never a path prefix. The
  endpoint itself accepts **any** path (even `/`), it validates only the
  signature param — handy for replaying a captured signature via curl.
- The AdScore signature **prefix varies with the environment** while staying
  valid (`BQOC` win-spoof, `BQOi` persistent profile, `BQNy` linux profile,
  `BQP…` vanilla Chromium). Log `sig[:12]` + `len` on every run: a changed
  prefix proves AdScore re-scored the new environment; an unchanged
  `result:0` across all of them means the block is upstream of the prefix
  (verdict threshold, dayparting or empty inventory).
- Engine config is embedded in the page as `window.<32-hex> = [[key,value],…]`
  with **arithmetic-obfuscated values** (`siteId: 528+847*339-221+5038949`),
  and only on the page(s) that include the loader — article/subpages may ship
  **no scripts at all**, so multi-page "warm-up" navigations off the armed page
  produce no inventory requests. Read the config from the HTML with curl
  before planning any browser run: `blockedCountries`, `trafficType`,
  `prepop`, `default` (fallback) — their absence is itself information.
- Camoufox persistent profile: `AsyncCamoufox(persistent_context=True,
  user_data_dir=...)` (both args; `persistent_context=PATH` raises
  TypeError, `user_data_dir` alone launches a non-persistent browser and
  also raises). The context is returned directly — use `ctx.pages`, not
  `browser.new_context()`.
- Elimination protocol that produced a clean verdict in one session (all
  `result:0`, direct datacenter IP unless noted): vanilla Chromium →
  Camoufox win-spoof → + jittered OS-cursor clicks, scrolls, 85 s dwell →
  clean FR residential (Free SAS Paris) via proxy → persistent profile with
  2 visits 8 min apart → `referer="https://www.google.com/"` → honest
  `os="linux"` (UA/TCP coherence) → `canvas_noise=False` stock canvas →
  curl replay of a fresh signature on 3 paths. If a human user on a
  VPN-flagged IP still gets pops while this whole matrix returns `result:0`,
  the remaining hypotheses are **dayparting/budget exhaustion** (schedule
  cron re-tests at evening hours) or an AdScore verdict component that
  cannot be reached from inside the browser (e.g. server-side TLS/TCP
  fingerprint of the JSONP request vs the OS claimed in the signature).

## SOLVED — the two-condition recipe that fires the pop (result:1 + popup)

Proven by A/B on the same exit IP, same minute, same behavior:

1. **Coherent environment**: `os="linux"` on the Linux host (NO OS spoof)
   **and** `canvas_noise=False, i_know_what_im_doing=True` (stock canvas, no
   RFP-style readback noise). The Windows spoof on a Linux TCP/Xvfb stack is
   what AdScore punishes — A/B proof: same clean French residential exit
   gave `result:1`+popup with coherent Linux and `result:0` with
   `os="windows"`.
2. **A residential exit whose AdScore history is clean** — this is per-IP,
   not per-ISP: 2 successes out of 11 French residential sessions (Orange
   fixed `92.184.125.35`, Free Mobile `37.167.73.174`), while Bouygues, SFR,
   Free fixed and other Orange exits all returned `result:0` with the
   identical winning config. Datacenter IPs fail even with the coherent
   stack. Practical loop: rotate proxy sessions, abort each run as soon as
   the first inventory response reads `result:0` (~25 s, page-load cost
   only), keep the session alive only when `result:1` appears.

Popunder window choreography once it fires: popup opens `about:blank`, then
**loads the site itself** (window-swap: the popup re-arms the engine and
issues its own inventory request) while the campaign URL
(`displayvertising.com/?kg=<token>` / `?it=<token>`) is assigned to the flow
— don't expect the popup URL to be the campaign URL; grep the inventory
body for it instead.

## AdScore internals (a.js decompiled probe map) + IP gate conclusion

The `c.adsco.re` script (~98 KB) runs 38 environment probes `s0`-`s37` and 32
async probes `ai0`-`ai31`. The ones that matter for OS/coherence spoofing:
`s7` error-stack format, `s10` Intl timezones/currencies, `s14`
`toLocaleString`, `s15` real font metrics (offsetWidth/Height), `s16` Math
libm hash (OS-dependent!), `s26` prototype-chain integrity (spoof
detection), `s34`-`s36` WebGL renderer + getParameter call-rate + shader
precision, `s25` scan for window/document/navigator keys starting with `_`/
`$cd` or exactly 28 chars (automation globals incl. `__pwInitScripts`,
`__playwright_builtins__`, `_phantom`, `_selenium`), `s24` window.open
popup-blocker behavior. `ai9`/`ai23` count mouse/pointer events, `ai25`
rAF timing, `ai14`-`ai17` reach 4/6.adsco.re:2087 (multi-endpoint IP
coherence), `ai30`/`ai31` WebRTC data.

Final verdict after the full elimination matrix: automation markers were
clean, coherent Linux env passed the probe layer, 360 s of behavioral
collection did NOT change the verdict — on a datacenter IP (M247, VPN
range) the answer stays `result:0` forever. The IP gate at the server is
independent of everything client-side: datacenter/VPN-range IP = no
inventory, private clean residential IP = inventory (2/11 sessions, the
failures being public-list or recycled exits whose AdScore history is
tainted). A proxy that appears on ANY public proxy list is effectively
pre-flagged, even when ip-api shows proxy:false.

## OS solution validated across independent hard sites (2026-11-12)

The coherent-Linux recipe (`os="linux"` + `canvas_noise=False` + geoip, no
OS spoof) was re-tested against every hard public detector — all pass:
incolumitas `os_mismatch:false` + relay `flagged:false` (its TCP section
exposes the exact mechanism: p0f-style SYN capture, `avg_score_os_class`
Linux 11.78/20.5 vs Windows 3.65 for stack `MSTNW`/TTL 50/window 64860 —
the site compares this to the UA's claimed OS), deviceandbrowserinfo
"You are human!", iphey "Trustworthy" MX 100 (previously overlay-blocked —
a plain visit now runs the scan), sannysoft all-pass, BrowserScan 90%
authenticity, creepjs clean, JA3/JA4/Akamai coherent.

Implication: OS spoofing on a mismatched host is dead — the SYN-level
classification cannot be patched from inside the browser. Either run the
honest OS, or move the whole session to a host whose stack matches the
claim (real Windows machine / Windows exit). A `webDriverAdvanced: FAIL`
may still appear on incolumitas' Intoli block while everything else
passes; treat it as noise unless a site acts on it.

Also: Camoufox DOES fake the faked-able physics (bundled fontconfig makes
claimed OS fonts render with real metrics, `windows-crt-math.patch` fixes
Math/libm hashes, fpgen draws credible GPU strings) — the only unfakeable
layer is pixel rasterization + kernel TCP, both host-bound.

Page-context matters as much as the browser: the same session/IP/config
that always returned `result:0` on a PopAds-style inventory started
returning `result:1` right after the target page dropped its third-party
ad banner (a-ads), images and webfonts. AdScore reads performance resource
entries (its `s21` probe) — a third-party AD domain in the page's resource
list is itself a signal. Slim pages help verdicts.

## OS spoofing CAN pass: match the claim to the exit's stack (2026-11-12)

`os_mismatch` on incolumitas is NOT a UA-vs-TCP string comparison. Their
`tcpip.incolumitas.com/classify` API exposes the real mechanism: a
HistGradientBoosting "relay" model over TCP features + the UA's claimed
OS class; `os_mismatch = relay.flagged` (threshold 0.8). Training data is
labelled by the UA's claimed OS, so stacks that real Windows users sit
behind become "acclimatized" to Windows claims.

Measured relay probabilities (same Linux-classified stacks):
- direct M247 stack (M1380,S,T,N,W10, TTL50) + Windows claim -> 0.949 FLAG
- Zenlayer DE datacenter proxy (M1460,S,T,N,W9, TTL45) + Windows -> 0.711 pass
- Asianet IN residential proxy (M1460,S,T,N,W10, TTL55, win 64240)
  + Windows claim -> 0.052 PASS, + Linux claim -> 0.097 PASS
  (browser run: os=windows -> os_mismatch:false; os=linux -> false)

Recipe: screen public proxies with one classify call per proxy per UA
(`curl -x proxy -A "<UA>" https://tcpip.incolumitas.com/classify?by_ip=1&detail=1`,
read `relay.probability`), keep proxies scoring < ~0.3 for the OS you want
to claim, then browse through them with that OS spoofed. Residential-ISP
CGNAT/router stacks are the goldmine; raw datacenter stacks sit at 0.7-0.78
(dangerously near 0.8).

Caveats: the model catches spoofed Windows claims 96% overall — only
acclimatized stacks beat it. This defeats the TCP/relay layer only; canvas
pixels and other physical probes still betray a Linux host when claiming
Windows, so prefer claiming Linux unless the site relies on the relay check.
Signal weights if building your own stack: tcp_options 0.991,
ip_total_length/tcp_off 0.95, window_scaling 0.77, ip_id 0.71, ttl 0.56.

## Explicit fingerprint path = 100% human-under-proxy (2026-11-12, AdScore live lab)

Controlled experiment on a self-operated AdScore site (hozakuwe.github.io,
AdscoreInit in head, PopCash pop engine) from a flagged datacenter IP
(M247, proxy:true). Dashboard counts scans, not visits. Batches sized
16/8/4/2/1 (unique subset sums) so the dashboard delta decodes which
batch passed:

- explicit fingerprint path (`generate_fingerprint(os='macos')` passed as
  `fingerprint=fp`): 24/24 classified human-under-proxy, both with FIXED
  and RANDOMIZED human behavior
- launcher-internal path (`os='macos'`): 6/11 (~55%) - the launcher adds
  an intermittent artifact
- `os='windows'` claim: 0/4 even with corrected window geometry - the
  Windows claim is dead on a Linux host regardless (relay model ~0.95)
- persistent identity (same fp twice): 2/2
- canvas noise (forced for foreign-OS claims) does NOT disqualify:
  noisy sessions classified human
- window geometry matters as a baseline: viewport 1280x720 on a 1366x900
  Xvfb gives a ~104px chrome margin (realistic); 1366x768 makes
  innerHeight > availHeight (impossible, instant bot)

Recipe: generate the fingerprint explicitly, pass it via `fingerprint=`,
viewport 1280x720, geoip=True, human mouse/scroll, single page per scan.
The pop itself still requires user activation (a click) - the positive
verdict alone never fires it.

## Windows claim: definitively dead on a Linux host (2026-11-13, 315-test sweep)

Blind sweep on the live AdScore lab, all variations bot (dashboard-confirmed):
explicit fingerprint path x80 (the recipe that scores 24/24 human on macos),
randomized/slow/minimal behavior x120, humanize x40, persistent identity x30,
corrected viewport x30, internal-path control x15. Zero human classifications.

Conclusion: the Windows claim fails on a Linux host regardless of every
browser-side variable - the contradiction is the network stack itself
(Linux TCP under a Windows claim, relay-model probability ~0.95), not
cosmetics. Perfect A/B: same IP, same method, same behavior - macos 24/24
human, windows 0/319. Only real fixes: run the browser on actual Windows,
or exit through a genuine Windows machine. Otherwise claim macos (or linux).

## Headless SOLVED: the screen draw was the variable (not chance)

The ~50% headless pass rate was screen-draw dependent, not random. In
headless mode Camoufox skips the display clamp (get_screen_cons returns
None), so each run reports its fingerprint's randomly drawn screen.
Dashboard-decoded results (unique batch sizes 5/7/3, one aggregate read):

- virtual + screen fixed 1440x900: 15/15 human-under-proxy  <- farm recipe
  (9/9 discovery + 6/6 confirmation block)
- headless + screen fixed 1440x900: 12/12 (8/8 + 4/4 confirmation)
- headless + screen fixed 1512x982: 0/6 (window not maximized:
  outerHeight 885 < availHeight 906 - suspicious geometry)
- virtual + 1512x982: 3/3 (virtual maximizes the window, geometry coherent)
- 1296x810: not a real Mac resolution - 1 bot (likely the single failure
  in a 12-scan mixed batch)

Rule: 1440x900 (MacBook Air) is statistically invisible; fake Mac
resolutions fail. Use headless='virtual' + CAMOUFOX_VIRTUAL_DISPLAY_SIZE
+ fingerprint screen pinned to 1440x900. Plain headless only with a
pinned 1440x900 screen. Unpinned draws = coin flip. NOTE: headless
launches need no DISPLAY, headed launches silently fail without one.

## Persona diversity is free (2026-11-13, dashboard-confirmed)

16 unique personas (varying GPU draws: Apple M1 / Intel HD / Radeon HD 3200 /
GeForce GTX 980 / Radeon R9; varying Firefox UAs; macos x10 at 1440x900,
linux x6 at 1920x1080, all headless='virtual'): 16/16 human-under-proxy,
including the "incoherent" Radeon-on-Mac draws. Combined validated recipes:
headed Xvfb 28/28, virtual macos 25/25, headless macos 12/12, linux 6/6.
Universal rule: coherent OS claim (matches TCP) + real vendor screen
resolution + realistic window geometry = human verdict, everything else is
free to vary.
