# Changelog

All notable changes to You2.0 Social Brain (DoppleX).

## [1.0.0] - 2026-05-02

### Added

#### A. Alembic Database Migrations
- Added `alembic>=1.13.0` to core dependencies
- Initialized Alembic with `sqlite:///you2.db` configuration
- Created initial migration (`cc758a0e3df0`) covering all models
- `env.py` imports `Base.metadata` for autogenerate support

#### B. GUI Polish
- **Content Calendar**: Monthly grid in scheduler showing scheduled post counts per day with colored blocks
- **Post History Search**: Real-time search/filter by content with result count display
- **Keyboard Shortcuts**:
  - `Ctrl+1-9`: Switch tabs
  - `Ctrl+G`: Go to Generate tab
  - `Ctrl+P`: Go to Post Now (Generate tab)
  - `Ctrl+S`: Go to Scheduler tab
  - `Ctrl+H`: Go to History tab
  - `Ctrl+Q`: Quit application
- **Empty States**: Friendly icons and messages for no accounts, no posts, no scheduled items
- **Loading Spinners**: `ProgressRing` on generate, analyze, scrape, reply bot buttons with disable/enable states

#### C. Input Validation & Security
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
- `validate_no_sql_injection()`: SQL injection pattern detection
- `RateLimiter` class: Per-key rate limiting with configurable windows
- `rate_limit()` decorator for API operations
- `SAFE_MOODS` whitelist with custom mood sanitization

#### D. Auto-Updater
- New `utils/updater.py` checking GitHub releases API
- Version comparison using `packaging.Version`
- Settings tab integration with "Check for Updates" button
- Shows current version, latest version, release notes, download URL

#### E. Async I/O (from previous release)
- Full async conversion of OllamaBridge, XClient, BrainEngine, ContentGenerator, StyleLearner, VectorStore, PipelineEngine, XReplyBot
- `aiohttp` for all HTTP clients
- GUI async handlers with loading spinners
- CLI async support via `command_wrapper`
- APScheduler sync wrappers using `asyncio.run()`

### Changed
- Updated `README.md` features list with all new capabilities
- Updated `AGENTS.md` with async architecture, Alembic workflow, validation guidelines
- Updated test count requirement: 20 tests must pass (was 12)

### Fixed
- Fixed SQLAlchemy 2.0 style (`db.get(Model, id)` instead of `db.query(Model).get(id)`)
- Fixed `datetime.utcnow()` deprecation → `utc_now()` helper
- Fixed import paths with `sys.path` bootstrap in `main.py`, `cli.py`, `tests/conftest.py`
