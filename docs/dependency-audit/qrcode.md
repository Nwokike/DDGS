# Dependency Audit: qrcode 8.2

- Installed version: 8.2 (uv.lock:1171). Own deps: only `colorama` on win32.
- Why installed: TRANSITIVE via `flet_cli` (uv.lock:348 lists `qrcode` in flet-cli's deps). NOT in pyproject `dependencies` — DDGS never declared it. It rides along with the Flet dev/CLI toolchain.
- Current usage: **zero — `qrcode` is not imported anywhere in `src/`** (grep for `qrcode|QRCode|print_ascii|make_image` returns no hits).
- Environment: Pillow 12.3.0 present (via flet) → raster path works. `pypng` NOT installed → `PyPNGImage` path is dead. `lxml` present (accelerates SVG; stdlib fallback exists regardless).

## 1. COMPLETE API INVENTORY

- `QRCode(version, error_correction=M, box_size=10, border=4, image_factory, mask_pattern)` — central class; `version` 1–40 or None=auto-fit.
- `QRCode.add_data(data, optimize=20)` — appends payload; auto-splits into NUMBER/ALPHA_NUM/8BIT chunks for density (0 disables).
- `QRCode.make(fit=True)` — compiles modules; auto-selects minimum version and best of 8 mask patterns via `lost_point` scoring.
- `QRCode.make_image(image_factory, **kwargs)` — renders via factory; defaults to PIL if importable else PyPNG; drives `drawrect`/`drawrect_context` + `process` hooks.
- `QRCode.print_ascii(out, tty, invert)` — zero-dependency terminal QR using cp437 half-block chars (255/223/220/219), honors `border`.
- `QRCode.print_tty(out)` — ANSI-color terminal QR; raises `OSError` if stdout is not a tty.
- `QRCode.get_matrix()` — raw bool matrix including border (border=0 for bare); feeds any custom renderer (e.g. Flet CustomPaint).
- `QRCode.clear()` / `best_fit()` / `best_mask_pattern()` / `active_with_neighbors(row, col)` — reset, version solver, mask solver, 3×3 neighbor context for styled drawers.
- `qrcode.make(data, **kwargs)` — one-call factory: builds QRCode, adds data, returns image.
- `qrcode.run_example(data, ...)` — demo helper that builds and `.show()`s a code.
- `PilImage` (image/pil.py) — default raster; `fill_color`/`back_color` (incl. `transparent` RGBA); `save()` to PNG/JPEG/any PIL format; proxies unknown attrs to the PIL Image.
- `PyPNGImage` (image/pure.py, alias `PymagingImage`) — pure-python PNG via optional `pypng`; `needs_drawrect=False`; unusable here (pypng absent).
- `StyledPilImage` (image/styledpil.py) — module_drawer + color_mask + centered embedded logo (`embedded_image`/`_path`, `_ratio` default 0.25, `_resample` LANCZOS).
- `SvgFragmentImage` / `SvgImage` / `SvgPathImage` (single `<path>`, gap-free) / `SvgFillImage` / `SvgPathFillImage` — five SVG builders, stdlib-only (+lxml if present).
- PIL module drawers — `SquareModuleDrawer`, `GappedSquareModuleDrawer(size_ratio)`, `CircleModuleDrawer`, `RoundedModuleDrawer(radius_ratio, neighbor-aware)`, `VerticalBarsDrawer`, `HorizontalBarsDrawer`.
- SVG module drawers + aliases — `SvgSquareDrawer`, `SvgCircleDrawer`, `SvgPathSquareDrawer`, `SvgPathCircleDrawer`; string aliases `circle`, `gapped-circle`, `gapped-square` (StyledPilImage has no aliases; pass instances).
- Color masks — `SolidFillColorMask`, `RadialGradiantColorMask`, `SquareGradiantColorMask`, `HorizontalGradiantColorMask`, `VerticalGradiantColorMask` (sic, "Gradiant"), `ImageColorMask` (photo-textured modules).
- ECC levels — `ERROR_CORRECT_L` (7%), `M` (15%, default), `Q` (25%), `H` (30%); `exceptions.DataOverflowError` when payload exceeds v40.
- Encoding internals (util.py) — modes NUMBER/ALPHA_NUM/8BIT_BYTE (+KANJI const, unsupported by `QRData`); `optimal_data_chunks`, `QRData`, `BitBuffer`, `create_data`, `mask_func` ×8, BCH type-info/number, Reed-Solomon via base.py `RS_BLOCK_TABLE`.
- `qr` console script — full CLI: `--factory pil|png|svg|svg-fragment|svg-path`, `--factory-drawer`, `--optimize`, `--error-correction L/M/Q/H`, `--ascii`, `--output`; tty auto-detect; win32 colorama init.

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. "Open on phone" QR — encode any result URL and show `PilImage` PNG bytes in a Flet `Image` (memory) so desktop→mobile handoff is one scan; cheapest high-value win, uses only the default path.
2. ASCII QR in terminal diagnostics — `print_ascii()` needs no PIL/SVG/pypng; ideal for `--diagnose`/support-bundle output and headless runs.
3. Saved-file LAN handoff — QR-encode the download URL (or LAN address) of files from `media_downloader` so a phone on the same network fetches them directly.
4. Styled brand QR — `StyledPilImage` with `RoundedModuleDrawer` + gradient mask + embedded logo (forces H ECC) for shareable/on-brand codes in marketing surfaces.
5. Share-sheet PNG export — `PilImage.save(BytesIO)` hands OS share sheets a portable PNG without touching disk.
6. Dependency-free vector export — `SvgPathImage` single-path SVG for reports/docs; zero extra requirements, tiny output.
7. Bulk QR for scheduled-crawl feeds — `qrcode.make()` in a loop over feed URLs; avoid gradient masks here (per-pixel Python loops are slow).
8. Wi-Fi/proxy onboarding QR — encode `WIFI:T:...` or the proxy/PAC URL so test devices join the crawl network by scanning.
9. Custom Flet rendering — `get_matrix()` bool grid drives a `CustomPaint`/canvas renderer with full DDGS theming, no image pipeline at all.
10. Dev-tooling CLI — the `qr` entry point is already on PATH via flet_cli; usable in scripts for generating fixture codes.

## 3. GOTCHAS

- Raster REQUIRES Pillow — present (12.3.0) on desktop, but qrcode arrives via flet_cli (dev toolchain); verify it ships inside the built APK/mobile bundle before relying on `PilImage` on-device, else fall back to SVG/`print_ascii`.
- `PyPNGImage` is dead weight here — `pypng` not installed; `make_image` default always resolves to PIL in this env.
- Embedded logo mandates `ERROR_CORRECT_H` (`ValueError` otherwise); logo placement does no legibility check — keep ratio small, test-scan.
- Long result URLs + H ECC force large versions (denser, harder to scan); prefer M for plain URL codes, shorten URLs first.
- `print_tty` raises `OSError("Not a tty")` on pipes; use `print_ascii` (or `--ascii`) for redirected/logged output.
- SVG output prefers lxml but works on stdlib ElementTree; nothing to install either way.
- Core encode is pure python (Android-safe); `StyledPilImage` color masks loop per-pixel in Python — slow on large `box_size`/bulk jobs.
- `QRData` raises on KANJI mode and rejects data that can't fit the forced mode; leave `mode=None`/default optimizer alone unless needed.
- Spec quiet-zone is `border=4` (default); lowering it saves space but breaks strict scanners.

## 4. COVERAGE

- Files read: 24/34 (every runtime module: `__init__`, `main`, `constants`, `util`, `exceptions`, `base`, `LUT` (partial — lookup tables skimmed), `console_scripts`, `release`, `compat/etree`, `compat/png`, `image/base`, `image/pil`, `image/pure`, `image/styledpil`, `image/svg`, `styles/colormasks`, `styles/moduledrawers/base|pil|svg`, plus 3 empty `__init__` namespace files).
- Not read: 10/34 — all under `tests/` (`test_qrcode`, `test_qrcode_pil`, `test_qrcode_pypng`, `test_qrcode_svg`, `test_example`, `test_script`, `test_util`, `test_release`, `consts`, `__init__`); behavior verified from source, not tests.
- Currently imported anywhere in `src/`? **No — zero hits.**
