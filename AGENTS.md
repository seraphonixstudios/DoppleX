# AGENTS.md — You2.0 Social Brain

**Version**: 1.0.0 | **Last Updated**: 2026-05-02

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
│   ├── db/database.py            # SQLite engine, SessionLocal, init_db
│   ├── brain/                    # AI generation pipeline
│   │   ├── brain.py              # BrainEngine: post/reply generation with RAG
│   │   ├── generator.py          # ContentGenerator: generate_and_store, regenerate
│   │   ├── style_learner.py      # Analyzes posts → style profile
│   │   └── ollama_bridge.py      # HTTP client for Ollama API
│   ├── embeddings/
│   │   └── vector_store.py       # Cosine similarity over post embeddings
│   ├── x_api/
│   │   └── x_client.py           # X API v2 + OAuth 1.0a media upload
│   ├── tiktok/
│   │   └── tiktok_client.py      # Playwright-based TikTok upload + scraping
│   ├── platforms/                # Thin wrappers around API clients
│   │   ├── x_poster.py
│   │   ├── x_scraper.py
│   │   ├── x_reply_bot.py
│   │   ├── tiktok_poster.py
│   │   └── tiktok_scraper.py
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
│   │   ├── matrix_banner.py
│   │   ├── dialogs.py
│   │   └── tray_manager.py       # System tray background operation
│   ├── prompts/
│   │   └── prompt_builder.py
│   └── utils/                    # Cross-cutting utilities
│       ├── logger.py             # Rotating file + console logging
│       ├── audit.py              # DB audit logging
│       ├── time_utils.py         # UTC helper (replaces datetime.utcnow)
│       ├── error_handler.py      # ErrorContext + safe_call + recovery hints
│       ├── validators.py         # Input sanitization + SQL injection guards + rate limiting
│       ├── updater.py            # GitHub release update checker
│       └── log_export.py
├── tests/                        # pytest test suite
│   ├── conftest.py               # Path bootstrapping + Ollama mock
│   ├── test_content_generator.py
│   ├── test_end_to_end.py        # Full lifecycle + pipeline + dry-run
│   ├── test_error_handler.py
│   ├── test_oauth_flow.py
│   ├── test_packaging.py
│   ├── test_tiktok_end2end.py
│   └── test_tiktok_live_dryrun.py
├── pack.py                       # PyInstaller build script
├── pyproject.toml                # pip installable package metadata
├── requirements.txt              # Core deps only
├── requirements-gui.txt          # flet
├── requirements-tiktok.txt       # playwright
├── requirements-x.txt            # requests-oauthlib
├── requirements-dev.txt          # pytest, ruff, pyinstaller
├── dist/                         # Built EXE (ignored by git)
├── build/                        # PyInstaller temp files (ignored)
└── README.md
```

---

## Build & Test

### Run Tests
```bash
pytest tests/ -v
```
All 20 tests must pass before committing.

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

---

## Common Tasks for Agents

### Adding a New CLI Command
1. Add `@cli.command()` decorated function to `src/cli.py`
2. Use `click.option()` and `click.argument()` for params
3. Add dry-run check: `if settings.use_dry_run: click.echo("[DRY RUN] ..."); return`
4. Add test to `tests/test_end_to_end.py`
5. Update README.md CLI commands section
6. Run tests: `pytest tests/ -v`

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

---

## Known Limitations

- No Docker image yet
- CI workflow file exists but pushing it requires a PAT with `workflow` scope
- X media upload requires OAuth 1.0a credentials separate from OAuth 2.0 bearer token
- TikTok posting requires Playwright browser installation
- Image generation requires local Stable Diffusion WebUI running

---

## Contact / Repo

- **Repo**: https://github.com/seraphonixstudios/DoppleX
- **License**: MIT
