# AGENTS.md — You2.0 Social Brain

**Version**: 1.0.0 | **Last Updated**: 2026-05-06

Project context for AI coding agents working on this codebase.

---

## Project Overview

You2.0 Social Brain (repo: DoppleX) is a fully local, AI-powered social media management tool. It clones your writing style using Ollama (local LLM) and automates posting to X/Twitter and TikTok.

**Key principle**: Everything runs on the user's machine. No cloud LLMs, no external data leakage.

---

## Directory Layout

```
.
├── src/                          # All source code
│   ├── main.py                   # Flet desktop GUI entry point
│   ├── cli.py                    # Click-based CLI entry point
│   ├── models.py                 # SQLAlchemy ORM models
│   ├── config/settings.py        # Settings with disk persistence
│   ├── db/database.py            # SQLite engine, SessionLocal, init_db, Alembic env
│   ├── brain/                    # AI generation pipeline
│   │   ├── brain.py              # BrainEngine: post/reply generation with RAG
│   │   ├── generator.py          # ContentGenerator: generate_and_store, regenerate
│   │   ├── style_learner.py      # Analyzes posts → style profile
│   │   └── ollama_bridge.py      # Async HTTP client for Ollama API (aiohttp)
│   ├── embeddings/
│   │   └── vector_store.py       # Cosine similarity over post embeddings
│   ├── x_api/
│   │   └── x_client.py           # X API v2 + OAuth 1.0a media upload (aiohttp)
│   ├── tiktok/
│   │   └── tiktok_client.py      # Playwright-based TikTok upload + scraping
│   ├── platforms/                # Thin wrappers around API clients
│   │   ├── x_poster.py
│   │   ├── x_scraper.py
│   │   ├── x_reply_bot.py
│   │   ├── tiktok_poster.py
│   │   └── tiktok_scraper.py
│   ├── pipeline/
│   │   └── pipeline.py           # PipelineEngine: full async content pipeline
│   ├── scheduler/
│   │   └── scheduler.py          # APScheduler: post scheduling, reply bot intervals
│   ├── oauth/                    # OAuth 2.0 + PKCE flow
│   │   ├── oauth_config.py
│   │   ├── oauth_flow.py
│   │   └── oauth_manager.py
│   ├── encryption/
│   │   └── crypto.py             # Fernet encryption for credentials
│   ├── security/
│   │   └── token_store.py        # Keyring fallback to file storage
│   ├── analytics/
│   │   └── metrics.py            # Post counts, engagement, top posts
│   ├── image_gen/
│   │   └── sd_client.py          # Stable Diffusion WebUI API client
│   ├── ui/                       # Flet UI components
│   │   ├── matrix_banner.py      # Matrix rain header with glitch effects
│   │   ├── cyber_theme.py        # Sci-fi theme system: colors, fonts, neon cards
│   │   ├── dialogs.py
│   │   ├── dev_console.py        # Developer console overlay (Ctrl+Shift+D)
│   │   └── tray_manager.py       # System tray background operation
│   ├── prompts/
│   │   └── prompt_builder.py
│   └── utils/                    # Cross-cutting utilities
│       ├── logger.py             # Rotating file + console logging
│       ├── audit.py              # DB audit logging
│       ├── time_utils.py         # UTC helper (replaces datetime.utcnow)
│       ├── error_handler.py      # ErrorContext + safe_call + recovery hints
│       ├── validators.py         # Input sanitization + SQL injection guards + rate limiting
│       ├── diagnostics.py        # System health checks, log summary
│       ├── updater.py            # GitHub release update checker
│       └── log_export.py
├── tests/                        # pytest test suite (104 tests)
│   ├── conftest.py               # Path bootstrapping + Ollama mock
│   ├── test_content_generator.py
│   ├── test_end_to_end.py        # Full lifecycle + pipeline + dry-run
│   ├── test_error_handler.py
│   ├── test_oauth_flow.py
│   ├── test_packaging.py
│   ├── test_tiktok_end2end.py
│   ├── test_tiktok_live_dryrun.py
│   ├── test_pipeline.py          # Queue, bulk, retry, best-time, cross-post
│   ├── test_edge_cases_and_errors.py  # Validation, async errors, GUI bootstrap
│   └── test_diagnostics.py       # Health checks, system info
├── pack.py                       # PyInstaller build script
├── pyproject.toml                # pip installable package metadata
├── requirements.txt              # Core deps only
├── requirements-gui.txt          # flet
├── requirements-tiktok.txt       # playwright
├── requirements-x.txt            # requests-oauthlib
├── requirements-dev.txt          # pytest, ruff, pyinstaller
├── alembic/                      # Alembic migrations
│   ├── env.py
│   ├── versions/
│   └── alembic.ini
├── dist/                         # Built EXE (ignored by git)
├── build/                        # PyInstaller temp files (ignored)
├── README.md
├── CHANGELOG.md
└── AGENTS.md
```

---

## Build & Test

### Run Tests
```bash
python -m pytest tests/ -v
```
All **104 tests** must pass before committing.

### Build EXE (Windows)
```bash
python pack.py
```
Output: `dist/You2SocialBrain.exe`

### Install from Source
```bash
# Core only
pip install -e .

# Full features
pip install -e ".[all]"
```

---

## Code Style & Conventions

- **Python**: 3.12+, tested on 3.14
- **SQLAlchemy**: 2.0 style. Use `db.get(Model, id)`, never `db.query(Model).get(id)`
- **Datetime**: Use `utc_now()` from `utils.time_utils`, never `datetime.utcnow()`
- **Imports**: Absolute imports from `src/` root. `sys.path` is bootstrapped in `main.py`, `cli.py`, and `tests/conftest.py`
- **Optional deps**: Guard with `try/except` or import inside functions (flet, playwright, requests-oauthlib)
- **Error handling**: Use `utils.error_handler.safe_call()` for operations that might fail
- **Logging**: Use `utils.logger.get_logger("you2.module_name")`
- **Encryption**: Use `encryption.crypto.encrypt/decrypt` for all credential storage
- **Thread safety**: Flet is NOT thread-safe. All UI updates from background threads must use `page.run()`
- **Async**: All new API/client code must be async using `aiohttp`. Playwright stays sync with `asyncio.to_thread()`
- **Flet API**: Use `ft.Colors` (not `ft.colors`), `ft.Icons` (not `ft.icons`), `ft.border_radius.all(2)` (not callable module)
- **Windows**: `PYTHONIOENCODING=utf-8` set when `sys.platform == "win32"` and `"pytest" not in sys.modules`

---

## Architecture Decisions

1. **No cloud LLMs**: Ollama only. Privacy-first.
2. **SQLite over Postgres**: Zero-config local persistence.
3. **Flet over Electron/Tauri**: Pure Python desktop UI, single toolchain.
4. **Click over argparse**: Better help text, subcommands, options.
5. **Modular requirements**: Core deps are minimal. GUI/TikTok/X are optional extras.
6. **Dry-run mode**: Global `--dry-run` flag for safe testing without API calls.
7. **Settings persistence**: JSON file in platform data dir, survives restarts.
8. **Async I/O everywhere**: `aiohttp` for all HTTP clients (Ollama, X API). GUI stays responsive. APScheduler threads use `asyncio.run()` for async code.
9. **Alembic migrations**: Schema changes managed via Alembic. `alembic upgrade head` on startup.
10. **Defensive validation**: All user inputs sanitized via `utils.validators`. SQL injection guards, rate limiting, platform-specific length checks.
11. **System tray integration**: GUI minimizes to tray, scheduler keeps running in background.
12. **Thread-safe UI updates**: Background threads (Ollama status checker) use `page.run()` to marshal UI updates to the main thread. Direct `page.update()` from threads causes crashes.
13. **Force exit fallback**: `os._exit(0)` after graceful cleanup to guarantee process termination on Windows.
14. **Developer Console**: In-app debug overlay (Ctrl+Shift+D) captures logs, unhandled exceptions, and system info.

---

## Common Tasks for Agents

### Adding a New CLI Command
1. Add `@cli.command()` decorated function to `src/cli.py`
2. Use `click.option()` and `click.argument()` for params
3. Add dry-run check: `if settings.use_dry_run: click.echo("[DRY RUN] ..."); return`
4. Add test to `tests/test_end_to_end.py` or `tests/test_pipeline.py`
5. Update README.md CLI commands section
6. Run tests: `python -m pytest tests/ -v`

### Adding a New Platform
1. Create API client in `src/<platform>_api/`
2. Create thin wrappers in `src/platforms/<platform>_<action>.py`
3. Add account fields to `src/models.py` if needed
4. Wire into `src/scheduler/scheduler.py` `_publish()` method
5. Add CLI commands to `src/cli.py`
6. Add GUI tab to `src/main.py`

### Modifying Models
1. Edit `src/models.py`
2. Run `alembic revision --autogenerate -m "Description"` to create migration
3. Run `alembic upgrade head` to apply migration
4. Update `alembic.ini` if database path changes

### Adding GUI Polish
1. Use `src/ui/cyber_theme.py` components: `neon_card`, `neon_button`, `ghost_button`, `neon_input`, `terminal_container`, `status_badge`
2. Add hover effects via `on_hover` + `_card_hover()` pattern in `main.py`
3. Use `MONO` font family for terminal aesthetic
4. Use `Neon.*` color constants for consistency
5. Empty states should have icon + title + subtitle + action button

---

## Known Limitations

- No Docker image yet
- CI workflow file exists but pushing it requires a PAT with `workflow` scope
- X media upload requires OAuth 1.0a credentials separate from OAuth 2.0 bearer token
- TikTok posting requires Playwright browser installation
- Image generation requires local Stable Diffusion WebUI running
- Flet `page.window.destroy()` is deprecated; use `page.window.close()`
- PyInstaller requires `--hidden-import` for dynamically imported packages (aiohttp, logging.handlers, packaging)

---

## Critical Context

- **104/104 tests passing**
- **Flet is NOT thread-safe**: All UI updates from background threads must use `page.run()` or `page.run_thread()`
- **Async methods require `await` everywhere**: `generate_and_store()`, `post_tweet()`, `upload_video()`, `scrape_x_history()`, `scrape_tiktok_history()`, `analyze_account()`, `run_once()`, `cross_post()`, `scrape_and_generate()`, `bulk_generate()`, `publish_queued()`
- **Click CLI async**: `command_wrapper` detects async callbacks and wraps with `asyncio.run()`
- **GUI async**: Flet `on_click` handlers can be `async def`; use `ProgressRing` + disable/enable buttons
- **Ollama bridge mocks in tests**: Must patch with `async def` coroutines, not lambdas
- **Project imports**: Absolute imports from `src/` root. `sys.path.insert(0, ...)` bootstrapped in `main.py`, `cli.py`, `tests/conftest.py`
- **SQLAlchemy style**: Must use `db.get(Model, id)`, never `db.query(Model).get(id)`
- **Datetime**: Must use `utc_now()` from `utils/time_utils`, never `datetime.utcnow()`
- **Alembic workflow**: Edit models → `alembic revision --autogenerate -m "desc"` → `alembic upgrade head`
- **Git push method**: `git push https://user:token@github.com/...` because `git push origin main` hangs on this machine
- **EXE build**: Run `python pack.py` after any code changes; output is `dist\You2SocialBrain.exe`
- **Background thread UI**: The Ollama status checker runs in a `threading.Thread` and uses `self.page.run(_update)` to safely update UI

---

## Contact / Repo

- **Repo**: https://github.com/seraphonixstudios/DoppleX
- **License**: MIT
