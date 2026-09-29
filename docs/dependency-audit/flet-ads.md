# flet_ads — Dependency Audit (DDGS capability utilization)

Package: `flet_ads` 1.0.1 (`flet_ads-1.0.1.dist-info`). No rewarded-video class; no refresh/sizing API beyond `width`/`height`; no assets or config files in package.
Consumer: DDGS (`src/services/ad_service.py`, `src/core/styles.py:build_banner_ad`, `src/screens/chat_screen.py`, `src/app_controller.py`, `src/components/wallet.py`, `src/components/results/downloader.py`).

Owner ad rules respected below: full-width no-label glass banners (Sherlock pattern), one ad after every AI reply, thread never ends on an ad, 90 s interstitial gap, production AdMob IDs live (`USE_TEST_IDS = False`).

## 1. COMPLETE API INVENTORY

### BaseAd (`base_ad.py`) — base of everything
- `unit_id: str` (required) — per-placement AdMob unit id. DDGS uses two: banner + interstitial (prod IDs in `AdService`).
- `request: AdRequest` (default `AdRequest()`) — targeting payload. DDGS never sets it (always default).
- Events: `on_load`, `on_error` (`e.data` = error info), `on_open` (fullscreen overlay opened — pause animations), `on_close` (overlay closed — resume), `on_impression`, `on_click`.
- `before_update()` — raises `ft.FletUnsupportedPlatformException` when `page.web` or `not page.platform.is_mobile()`. **Mobile-only (Android/iOS).**

### BannerAd (`banner_ad.py`) — `@ft.control("BannerAd")`, `ft.LayoutControl + BaseAd`
- Inline display banner. Inherits all `BaseAd` props/events plus `LayoutControl` sizing (`width`/`height`; DDGS pins `320x50`).
- `on_will_dismiss` — iOS only, before fullscreen dismiss.
- `on_paid: PaidAdEvent[BannerAd]` — estimated earnings event; **allowlisted accounts only**.
- Test IDs: Android `ca-app-pub-3940256099942544/9214589741`, iOS `.../2435281174` (replace in prod).
- Raises on web/non-mobile (inherited gate).

### InterstitialAd (`interstitial_ad.py`) — `@ft.control`, `ft.Service + BaseAd`
- Full-screen overlay. Must be added to `page.services`.
- **Single-use:** each instance `show()`s at most once; create a new instance per impression (DDGS `preload_interstitial` + re-preload in `_handle_close` already does this).
- `async show()` — present loaded ad; must be loaded first (`on_load` before `show`).
- Inherits `unit_id`/`request`/all `BaseAd` events. Test IDs: Android `.../1033173712`, iOS `.../4411468910`.
- Raises on web/non-mobile.

### NativeAd (`native_ad.py`) — `@ft.control("NativeAd")`, extends `BannerAd`
- `factory_id: str | None` — custom platform-view factory id.
- `template_style: NativeAdTemplateStyle | None` — managed template styling.
- `init()` raises `ValueError` unless at least one of `factory_id`/`template_style` is set.
- **Export gotcha:** NOT re-exported from `flet_ads/__init__.py` — must `from flet_ads.native_ad import NativeAd` (likewise `NativeAdTemplate*` live only in `flet_ads.types`).

### ConsentManager (`consent_manager.py`) — `@ft.control`, `ft.Service` (Google UMP)
- Flow: `request_consent_info_update(params?)` every launch → `load_and_show_consent_form_if_required()` → `can_request_ads()` gate.
- `is_consent_form_available() -> bool`, `get_consent_status() -> ConsentStatus`, `can_request_ads() -> bool`.
- `get_privacy_options_requirement_status() -> PrivacyOptionsRequirementStatus` + `show_privacy_options_form()` — persistent GDPR entry point.
- `reset()` — **testing only**, simulates first-time user; never in prod.
- Raises on web/non-mobile.

### types.py
- `PrecisionType`: `UNKNOWN | ESTIMATED | PUBLISHER_PROVIDED | PRECISE`.
- `PaidAdEvent`: `value: float`, `precision: PrecisionType`, `currency_code: str`.
- `AdRequest` (`@ft.value`): `keywords: list[str] | None`, `content_url: str | None`, `neighboring_content_urls: list[str] | None`, `non_personalized_ads: bool | None`, `http_timeout: int | None` (**Android only**, ms), `extras: dict[str,str] | None`.
- `NativeAdTemplateType`: `SMALL | MEDIUM`. `NativeTemplateFontStyle`: `NORMAL | BOLD | ITALIC | MONOSPACE`.
- `NativeAdTemplateTextStyle`: `size`, `text_color`, `bgcolor`, `style`.
- `NativeAdTemplateStyle`: `template_type` (default `MEDIUM`), `main_bgcolor`, `corner_radius`, `call_to_action_text_style`, `primary_text_style`, `secondary_text_style`, `tertiary_text_style`.
- `ConsentStatus`: `NOT_REQUIRED (outside regulated region) | OBTAINED (decision collected — NOT "granted") | REQUIRED | UNKNOWN`.
- `PrivacyOptionsRequirementStatus`: `NOT_REQUIRED | REQUIRED (must show persistent entry point) | UNKNOWN`.
- `DebugGeography`: `DISABLED | EEA | REGULATED_US_STATE | OTHER` (test devices only).
- `ConsentDebugSettings`: `debug_geography`, `test_identifiers` (simulators auto-registered; physical id from `adb logcat`/Xcode log).
- `ConsentRequestParameters`: `tag_for_under_age_of_consent` (`True` suppresses form — under-age can't consent), `consent_debug_settings`.

### Top-level exports (`__init__.py`)
Exports `AdRequest, BannerAd, BaseAd, ConsentDebugSettings, ConsentManager, ConsentRequestParameters, ConsentStatus, DebugGeography, InterstitialAd, PaidAdEvent, PrecisionType, PrivacyOptionsRequirementStatus`. Deliberately or accidentally absent: `NativeAd`, `NativeAdTemplateStyle`, `NativeAdTemplateTextStyle`, `NativeAdTemplateType`, `NativeTemplateFontStyle`.

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX/revenue impact)

What DDGS already uses: `BannerAd(unit_id, 320x50, on_error)` in glass wrapper; `InterstitialAd(unit_id, on_load/on_error/on_close)` + `show()` with 90 s gap and single-use re-preload; `ConsentManager.request_consent_info_update / load_and_show_consent_form_if_required / can_request_ads / get_privacy_options_requirement_status / show_privacy_options_form`; interstitial triggers (app_controller ×2, downloader download-complete); fake-rewarded interstitial → wallet credits; prod IDs; chat banner pool (ad after every AI reply, never last).

1. **NativeAd templates in results/chat feed** — `NativeAdTemplateStyle` (SMALL/MEDIUM, bgcolor, corner radius, CTA/primary/secondary/tertiary text styles) themed to the glass system would blend with result cards far better than fixed 320×50 and typically lifts CTR. Keeps owner rules intact if wrapped in the same full-width no-label glass and inserted positionally (never as last row). Note: import from `flet_ads.native_ad`/`types`, not top level.
2. **Impression/click/paid analytics** — `on_impression`, `on_click`, `on_open`, `on_paid` are never wired (banners pass only `on_error`; `get_banner_ad` even swallows with `lambda e: None`). Logging these gives per-placement yield, CTR, and revenue events (`PaidAdEvent.value/precision/currency_code`) with zero visual change.
3. **AdRequest targeting** — `request` is always default. `keywords` from the search/chat query, `content_url`/`neighboring_content_urls` for brand-safety, `non_personalized_ads=True` as EEA/consent fallback, `extras` for mediation, `http_timeout` for slow networks (Android). Expected eCPM lift on mobile with no layout change.
4. **Full UMP surface** — unused: `get_consent_status()`, `is_consent_form_available()` (proper load-gating instead of try/except default-allow), `ConsentRequestParameters.tag_for_under_age_of_consent`, `ConsentDebugSettings(debug_geography/test_identifiers)` for EEA QA, and a persistent privacy-options button in Settings (service method `show_privacy_options()` exists but no UI entry point found). `reset()` for QA only.
5. **Lifecycle/placeholder polish** — unused: banner `on_load` (shimmer → ad swap, error retry with backoff), interstitial `on_open` (pause downloads/timers/audio) vs only `on_close` resume, `on_will_dismiss` (iOS). No behavior-rule conflict; strictly robustness.

## 3. GOTCHAS
- **Desktop = no-op by design.** `BaseAd.before_update` / `ConsentManager.before_update` raise `FletUnsupportedPlatformException` on web or non-mobile. On Windows DDGS correctly returns an empty `Container` (`_is_mobile()` / platform guards) — zero desktop ad revenue, and `page.services` must not receive ad controls there.
- **Interstitial is single-use.** Re-`show()` on a shown/failed instance errors; always mint a fresh `InterstitialAd` (current code does). The 90 s gap is stamped only on real show (`state.last_interstitial_ts`).
- **No true rewarded API.** `show_rewarded_interstitial` is an `InterstitialAd` with `on_close` → grant credits. No server-side verification, no reward callback — grant-on-close can over-reward accidental closes; keep the no-ad → no-grant guard and consider capping (already 200/day + 30 s cooldown pattern noted in code).
- **No refresh-cadence or adaptive-size API.** Banner refresh is SDK-automatic; sizing is fixed `width`/`height` (320×50) — full-width look comes from DDGS's glass wrapper, not the SDK.
- **Consent semantics:** `OBTAINED` ≠ granted — check `can_request_ads()`, not status. `REQUIRED` privacy-options status obliges a persistent settings entry point (GDPR). `tag_for_under_age_of_consent=True` suppresses the form entirely.
- **Test-only traps:** `ConsentManager.reset()` and debug-geography/test IDs must never ship; `USE_TEST_IDS=False` is already correct with prod IDs active.
- **Play edition:** UMP consent + privacy-options entry point are the Play/EEA hard requirements; `non_personalized_ads` is the compliant fallback when consent is withheld. Rewarded-for-credits and interstitial frequency (90 s gap, not during AI streaming, not on every download) are the Play-policy-sensitive knobs — keep interstitials post-action (download-complete) rather than interruptive.

## 4. COVERAGE
- Files read: 7 / 7 `.py` (`__init__.py`, `banner_ad.py`, `base_ad.py`, `consent_manager.py`, `interstitial_ad.py`, `native_ad.py`, `types.py`). No assets/config files in package (only `__pycache__` + `flet_ads-1.0.1.dist-info`).
- DDGS consumer files grepped: `src/services/ad_service.py` (full read), `src/core/styles.py`, `src/screens/chat_screen.py`, `src/app_controller.py`, `src/components/wallet.py`, `src/components/results/downloader.py`, `src/services/premium_service.py`.
