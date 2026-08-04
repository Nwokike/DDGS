## Plan: Merge main into playstore with preserved features

### Step 1: Merge main into playstore
- `git checkout playstore && git merge main --no-commit --no-ff`
- Resolve conflicts: keep main's architecture for all files EXCEPT playstore-specific ones

### Step 2: Preserve playstore-specific features after merge

**File: `.github/workflows/build-all.yml`**
- Keep playstore's AAB-only workflow (no Windows/Linux jobs)
- Keep "(Play Store)" in release names
- Keep AAB build command

**File: `src/components/results/downloader.py`**
- Add YouTube download restriction dialog back
- When `is_youtube_url(result.url)` → show AlertDialog with "Open in YouTube" button
- Return early (no download)

**File: `src/components/settings/sections_about.py`**
- Add "Edition: Google Play Edition (Policy Compliant)" row in About section

**File: `README.md`**
- Keep Android-only downloads
- Remove Windows/Linux badges

**File: `pyproject.toml`**
- Upgrade to flet 0.86.5 (main's version) — BaseAd monkey-patch no longer needed
- Keep startup_screen config
- Update version to 1.2.0, build 3

### Step 3: Commit and test
- Verify app runs clean
- Verify YouTube restriction works
- Verify Edition label shows in Settings > About
- Verify SearchBar and all modern features work