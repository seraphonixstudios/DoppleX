# Changelog

All notable changes to You2.0 Social Brain (DoppleX).

## [1.0.0] - 2026-05-06

### Added

#### A. Sci-Fi Cyberpunk UI Theme
- New `ui/cyber_theme.py` with full theme system
- Neon color palette: Matrix green `#39FF14`, electric cyan `#00F0FF`, amber `#FFB000`, deep abyss `#0A0A1A`
- Monospace font styling throughout (Consolas / Courier New)
- `neon_card()` with glow shadow borders
- `terminal_container()` for panel styling
- `neon_button()` and `ghost_button()` with cyber styling
- `neon_input()` and `neon_dropdown()` with terminal aesthetic
- `status_badge()` with pulsing colors (ok/warning/error/info)
- `glitch_text()` with RGB-split shadow effect
- `scanline_overlay()` for CRT monitor effect
- `MatrixRainHeader` with katakana + random character background
- Card hover effects: border color intensifies, glow spreads on mouseover

#### B. Developer Console
- New `ui/dev_console.py` — overlay modal triggered by `Ctrl+Shift+D`
- Three tabs: Logs, Errors, System Info
- Auto-catches unhandled exceptions with full tracebacks
- Copy to clipboard functionality
- Clear console button
- Integrated with global `sys.excepthook` for automatic error capture

#### C. Diagnostics System
- New `utils/diagnostics.py` with comprehensive health checks
- `check_ollama()` — connection, model availability
- `check_database()` — SQLite connectivity, table integrity
- `check_accounts()` — count, active status, token expiry
- `check_x_api()` — bearer token validity
- `check_tiktok_browser()` — Playwright installation
- `check_stable_diffusion()` — WebUI connectivity
- `get_system_info()` — OS, Python version, memory, disk
- `get_log_summary()` — ERROR/WARNING counts from log files
- CLI `diagnose` command with `--json` export
- GUI Diagnostics tab with Run Diagnostics, Export JSON, filtered log viewer

#### D. Alembic Database Migrations
- Added `alembic>=1.13.0` to core dependencies
- Initialized Alembic with `sqlite:///you2.db` configuration
- Created initial migration (`cc758a0e3df0`) covering all models
- `env.py` imports `Base.metadata` for autogenerate support
- Auto-upgrade on app startup

#### E. GUI Polish & UX
- **Content Calendar**: Monthly grid in scheduler showing scheduled post counts per day with colored blocks
- **Post History Search**: Real-time search/filter by content with result count display
- **Neon Toast Notifications**: Styled SnackBar with icons, glow borders, dismiss button, 4s duration
- **Keyboard Shortcuts**:
  - `Ctrl+1-9`: Switch tabs
  - `Ctrl+G`: Go to Generate tab
  - `Ctrl+P`: Go to Post Now (Generate tab)
  - `Ctrl+S`: Go to Scheduler tab
  - `Ctrl+H`: Go to History tab
  - `Ctrl+Q`: Quit application
  - `Ctrl+Shift+D`: Developer Console
  - `Ctrl+?`: Help dialog
- **Empty States**: Friendly icons, titles, subtitles, and action buttons for no accounts, no posts, no scheduled items
- **Loading Spinners**: `ProgressRing` on generate, analyze, scrape, reply bot buttons with disable/enable states
- **Account Cards**: Platform-colored badges (X=cyan, TikTok=magenta), active/inactive status pills, hover glow
- **History Cards**: Platform badges, monospace content preview, timestamp, hover effects
- **Stat Cards**: Neon glow, monospace counters, uppercase labels, hover effects
- **Status Bar**: Badge-style status containers with neon borders and pulsing indicators
- **Welcome Screen**: Cyber-styled onboarding with action cards and quick tips

#### F. Input Validation & Security
- New `utils/validators.py` with comprehensive sanitization
- `sanitize_text()`: Strip, escape HTML, enforce length, remove control chars
- `sanitize_username()`: Validate social media username format
- `sanitize_platform()`: Normalize platform names (Twitter → X)
- `sanitize_token()`: Validate API token format, reject placeholders
- `sanitize_file_path()`: Prevent directory traversal attacks
- `sanitize_hashtags()`: Clean and limit hashtag lists (max 30)
- `sanitize_schedule_date()`: Parse dates, enforce future-only scheduling
- `validate_post_content()`: Platform-specific length limits (X: 280, TikTok: 2200)
- `validate_account_id()`, `validate_positive_int()`
- `check_sql_injection()`: SQL injection pattern detection
- `RateLimiter` class: Per-key rate limiting with configurable windows
- `rate_limit()` decorator for API operations
- `SAFE_MOODS` whitelist with custom mood sanitization

#### G. Auto-Updater
- New `utils/updater.py` checking GitHub releases API
- Version comparison using `packaging.Version`
- Settings tab integration with "Check for Updates" button
- Shows current version, latest version, release notes, download URL

#### H. Async I/O Conversion
- Full async conversion of OllamaBridge, XClient, BrainEngine, ContentGenerator, StyleLearner, VectorStore, PipelineEngine, XReplyBot
- `aiohttp` for all HTTP clients (Ollama, X API)
- GUI async handlers with loading spinners
- CLI async support via `command_wrapper`
- APScheduler sync wrappers using `asyncio.run()`
- Playwright stays sync with `asyncio.to_thread()` wrappers

#### I. Thread Safety & Stability
- Background Ollama status checker uses `page.run()` for UI updates (not direct `page.update()`)
- `_shutdown` flag on background thread for clean exit
- `_exit_app()` uses `page.window.close()` (not deprecated `destroy()`)
- Robust cleanup with try/except around tray.stop(), scheduler.shutdown(), window.close()
- `os._exit(0)` fallback to guarantee process termination

#### J. PyInstaller Build Fixes
- Added `--hidden-import aiohttp` to `pack.py`
- Added `--hidden-import logging.handlers` for rotating file handler
- Added `--hidden-import packaging` for version comparison
- Removed `background`/`on_background` from `ft.ColorScheme` (Flet 0.84 crash)
- `ft.colors` → `ft.Colors`, `ft.icons` → `ft.Icons`
- `ft.border_radius(6)` → `ft.border_radius.all(6)`

### Changed
- Updated `README.md` with all new capabilities, keyboard shortcuts, diagnostics
- Updated `AGENTS.md` with async architecture, Alembic workflow, validation, thread safety
- Updated test count: 104 tests must pass (was 20)
- Status bar redesigned with badge-style containers and monospace fonts
- Welcome screen restyled with cyberpunk typography
- Account form and OAuth panel use consistent terminal styling
- All card components use `ft.Container` instead of `ft.Card` for consistent cyber styling

### Fixed
- Fixed app freezing caused by background thread calling `page.update()` directly
- Fixed window close button not closing app (tray was intercepting close event)
- Fixed `ModuleNotFoundError: No module named 'aiohttp'` in PyInstaller EXE
- Fixed SQLAlchemy 2.0 style (`db.get(Model, id)` instead of `db.query(Model).get(id)`)
- Fixed `datetime.utcnow()` deprecation → `utc_now()` helper
- Fixed import paths with `sys.path` bootstrap in `main.py`, `cli.py`, `tests/conftest.py`
- Fixed Flet 0.84 API compatibility (Colors, Icons, border_radius)

## [0.9.0] - 2026-04-28

### Added
- Initial async I/O conversion
- Content queue workflow (draft/approve/publish)
- Bulk generation across topics
- Cross-posting to X and TikTok
- Auto-retry with exponential backoff
- Best time detection from analytics
- Full pipeline command (scrape → analyze → generate → queue)
- System tray integration
- Settings persistence

## [0.8.0] - 2026-04-15

### Added
- Initial Flet GUI with dashboard, accounts, style, generate, scheduler, history, analytics
- X/Twitter integration (OAuth 2.0, API v2, scraping, reply bot)
- TikTok integration (Playwright upload, scraping)
- Style learning from post history
- RAG memory with embeddings
- Image generation via Stable Diffusion
- Analytics dashboard
- Click CLI with 20+ commands
- PyInstaller build script
