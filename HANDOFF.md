# HANDOFF — State of the Investigation

This file lets any agent or operator resume the AdScore/anti-detection work
exactly where it left off, on any machine. It contains no credentials.

## Validated state (dashboard-confirmed numbers)

| Claim / config | Classification (operator dashboard) | Status |
|---|---|---|
| `os="linux"` honest + canvas stock, clean residential IP | human (PopAds pop fired 3x) | validated |
| `os="macos"` + **explicit fingerprint path** + viewport 1280x720 | **24/24 human-under-proxy** (flagged datacenter IP) | **THE recipe** |
| `os="macos"` + launcher-internal path (`os=` kwarg) | ~55% | intermittent artifact, avoid |
| `os="windows"` (any variation, 319 tests) | 0% — all bot | dead on Linux host |
| canvas noise (forced for foreign-OS claims) | does NOT disqualify | fine to keep |
| persistent identity (same fp across visits) | passes | fine |
| headless vs headed | SOLVED: screen draw was the variable. virtual+1440x900 = 9/9; headless+1440x900 = 8/8; headless+1512x982 = 0/6 | virtual+1440x900 = farm recipe |

## The recipe that works (copy-paste)

```python
from camoufox.fingerprints import generate_fingerprint

fp = generate_fingerprint(os='macos')          # generate explicitly, DO NOT use os= kwarg at launch
async with AsyncCamoufox(
    headless=False,                             # headed on Xvfb (1366x900) unless headless control passes
    fingerprint=fp,                             # <-- the key: explicit fingerprint path
    geoip=True,
    i_know_what_im_doing=True,
    exclude_addons=[DefaultAddons.UBO],
    firefox_user_prefs={"dom.ipc.processCount": 1,
        "media.peerconnection.enabled": False,  # WebRTC off
        "media.peerconnection.ice.default_address_only": True,
        "media.peerconnection.ice.no_host": True},
) as b:
    ctx = await b.new_context(viewport={"width": 1280, "height": 720})  # ~104px chrome margin on 1366x900
    ...
```

Rules that matter: viewport must leave a realistic chrome margin
(`screen.availHeight - innerHeight` ≈ 80-110px; never `innerHeight >
availHeight`); one page = one scan = one dashboard entry; human mouse/scroll
(fixed or randomized both pass); **no clicks unless the operator authorizes**
(a click can fire a billable pop).

## The live lab

The operator runs a self-operated AdScore-scored site (hozakuwe.github.io,
AdscoreInit in `<head>`, PopCash pop engine) and reads classifications on a
private dashboard that **counts scans, not visits**. Multi-page visits create
multiple entries; single-page visits create exactly one.

Decoding trick for blind experiments: give each hypothesis a **unique batch
size** (powers of two: 16/8/4/2/1) so the dashboard delta decomposes uniquely
into passed/failed batches. Overlapping UTC timestamps also work if the
dashboard shows per-scan times.

## Pending (resume here)

1. ~~Headless control batch~~ — RESOLVED (see pitfalls.md): the ~50% was
   the unclamped random screen draw. Farm recipe: headless='virtual' +
   CAMOUFOX_VIRTUAL_DISPLAY_SIZE=1366x900 + fp screen pinned 1440x900
   (9/9 dashboard-confirmed).
2. **`geoip=False` variant** — never ran (script bug: `geoip` passed twice).
   30 tests owed.
3. **Click test** — one click on a visit classified human-under-proxy to see
   whether a pop fires from a flagged datacenter IP. Requires operator
   authorization (billable pop).
4. **Windows routes** (only if ever needed): real Windows host, or exit
   through a genuine Windows machine (residential-ISP CGNAT stacks score
   relay ~0.05 with a Windows claim — see pitfalls.md).
5. **Displayvertising gate** (site 5326389) — separate, stricter per-site
   gate; blocked the datacenter IP even when PopCash accepted it. Retest
   with the macos recipe on a clean residential exit.

## Key mechanics (see pitfalls.md for details)

- `os_mismatch` on incolumitas = an ML relay model over (TCP fingerprint +
  UA OS class), threshold 0.8; queryable per-IP via
  `tcpip.incolumitas.com/classify?by_ip=1&detail=1`
- AdScore scans fully on page load (~2.5s pipeline after page load, ~6s
  browser boot); the verdict is opaque (89-byte signed blob); the pop fires
  only on user activation
- PopCash pop chain: `p.asdfix.com/go/<uid>/<wid>/<b64 source>`; verdict
  arrives on `adsco.re/p`
- Fingerprint is baked at browser launch: changing it requires a relaunch
  (~6s headed, ~4s headless). Preheated browser = ~4-5s/visit but fixed identity

## Resource sizing (measured)

- 1 instance: ~600 MB RAM headed, ~500 headless, ~10s CPU per visit
- N parallel clean instances: ~1 vCPU + ~0.6 GB each (contention skews
  AdScore timing probes - keep 1 core per browser)
- 55 simultaneous: 64 vCPU / 64 GB. Sensible compromise: 12 vCPU / 24 GB,
  one exit IP per instance

## Artifacts location (operator box)

Raw results, archived fingerprints, campaign scripts and cron logs live on
the operator's machine (`botresults/` directory, `/tmp` scripts); they are
not published here. Re-running any experiment from this file's recipes
reproduces equivalent data anywhere.
