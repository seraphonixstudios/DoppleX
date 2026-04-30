import sys
import os

# Add src/ to Python path so absolute imports work inside the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Patch detect_models before any modules import settings and try to hit Ollama
import config.settings as _settings_module
_settings_module.detect_models = lambda url: ("dummy-model", "dummy-embed")

from db.database import init_db

# Initialize the database before any tests run
init_db()
