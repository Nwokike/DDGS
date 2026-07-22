DDGS v1.1.0 — Desktop Platform Releases & Direct Video Downloading

Welcome to DDGS v1.1.0! This release brings native desktop applications for Windows and Linux, direct video downloading, and general bug fixes and performance improvements.

## Highlights

- **More Devices Supported** — Native desktop support for Windows (`DDGS.exe`) and Linux (`.deb`, `.rpm`, `.tar.gz`).
- **Direct Video Downloads** — Direct stream resolution and local media downloading for video search results.
- **Bug Fixes & Stability** — General UI responsiveness polish, performance optimizations, and bug fixes across all platforms.

---

### Release Notes

#### 1. Expanded Device Support (Windows & Linux)
- **Windows Setup Installer** — Automated standalone setup installer with desktop shortcut integration (`DDGS.exe`).
- **Linux Desktop Packages** — Native `.deb` packages for Ubuntu/Debian/Mint, `.rpm` packages for Fedora/RHEL, and universal `.tar.gz` portable archives.

#### 2. Direct Video Downloading
- **Direct Stream Resolution** — Resolves video watch links directly into playable media streams for local downloading.
- **Progress Tracking** — Live download progress indicators with native OS file picker save controls.

#### 3. Bug Fixes & Stability
- **Search & Performance Polish** — Improved overall UI responsiveness, search performance, and stability fixes across all platforms.

---

DDGS v1.0.0 — Initial Release

Welcome to the initial release of DDGS, a privacy-first mobile metasearch app built to bring fast, flexible search experiences to Android and other Flet-supported platforms. This first version combines a polished, mobile-friendly interface with deep search controls and page extraction tools, all designed to keep results local and user-driven.

## Highlights

- Search privately across 14 public search engines from one app
- Run web, image, video, news, and book searches from a single interface
- Extract webpage content as Markdown, plain text, rich text, HTML, or raw bytes
- Customize searches with safe search, region, backend, time limit, result count, and pagination controls
- Keep a local history of recent searches and inspect live activity logs
- Enjoy a guided onboarding experience with light, dark, and system theme support

---

### Core Features

#### 1. Privacy-First Metasearch
- **Multi-Engine Search** — Query across a wide range of providers, including DuckDuckGo, Google, Brave, Bing, Yahoo, Yandex, Startpage, Mojeek, Wikipedia, Grokipedia, and more.
- **Search Modes** — Switch between web, image, video, news, and book searches without leaving the app.
- **Backend Control** — Choose Auto mode or manually select a preferred search backend for each query type.

#### 2. Page Extraction and Content Fetching
- **URL Content Extraction** — Fetch and preview the contents of a web page in multiple formats such as Markdown, plain text, rich text, HTML, or raw bytes.
- **Local Saving** — Save extracted content or downloaded media directly from the app to the device.
- **Result Preview Flow** — Open result details, inspect links, and navigate through fetched content in a clean in-app experience.

#### 3. Advanced Search Controls
- **Safe Search** — Select off, moderate, or strict filtering modes.
- **Region Filtering** — Narrow results by region with support for multiple language and country presets.
- **Time Limits** — Filter results by day, week, month, or year.
- **Result Tuning** — Adjust maximum results, page number, and backend-specific search behavior.
- **Proxy & SSL Options** — Configure proxy usage and SSL verification for more controlled network environments.

#### 4. History, Logging, and Diagnostics
- **Search History** — Re-run previous searches quickly from a dedicated history view.
- **Activity Logs** — Review real-time in-app logs for searches, errors, and events.
- **Persistent Preferences** — Store theme, search settings, and history locally for a consistent experience.

#### 5. Mobile-First Experience
- **Clean Flet UI** — A modern, responsive interface with dedicated Home, Results, History, and Settings views.
- **Onboarding Flow** — Introduce key capabilities such as privacy, extraction, and advanced controls on first launch.
- **Theme Support** — Switch between light, dark, and system themes to suit your device and preference.

---

### Technical Foundation

- **Frontend** — Built with Flet on top of Flutter for a cross-platform mobile and desktop experience.
- **Search Core** — Uses the DDGS library to aggregate results from multiple public providers.
- **Networking** — Designed around the DDGS and primp stack for flexible HTTP behavior and diagnostics.
- **Storage** — Persists settings and history using a platform-safe local JSON storage approach.
- **Logging** — Includes in-memory and file-backed logging support for troubleshooting and debugging.

---

## Notes for This Release

- This is the initial public release and is intended for early feedback and refinement.
- Internet access is required for search and page extraction features.
- Search behavior depends on the target search engines, network conditions, and regional availability.
- No account registration is required, and search preferences and history are stored locally on the device.
