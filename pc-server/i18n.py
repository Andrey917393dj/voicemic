"""
VoiceMic Internationalization (i18n) System
Loads language JSON files and provides translated strings.
"""
import json
import os
import locale

LANG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")

# Supported languages
LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "ja": "日本語",
    "zh": "中文",
    "pt": "Português",
    "ko": "한국어",
    "uk": "Українська",
}

_current_lang = "en"
_strings = {}
_fallback = {}


def detect_system_language() -> str:
    """Detect system locale and return best matching language code."""
    try:
        sys_locale = locale.getdefaultlocale()[0] or ""
        code = sys_locale.split("_")[0].lower()
        if code in LANGUAGES:
            return code
    except Exception:
        pass
    return "en"


def load_language(lang_code: str) -> bool:
    """Load a language file. Returns True on success."""
    global _current_lang, _strings
    path = os.path.join(LANG_DIR, f"{lang_code}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            _strings = json.load(f)
        _current_lang = lang_code
        return True
    except Exception:
        return False


def _load_fallback():
    """Load English as fallback."""
    global _fallback
    path = os.path.join(LANG_DIR, "en.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                _fallback = json.load(f)
        except Exception:
            pass


def init(lang_code: str = None):
    """Initialize i18n with given or auto-detected language."""
    _load_fallback()
    if lang_code is None:
        lang_code = detect_system_language()
    if not load_language(lang_code):
        load_language("en")


def t(key: str, **kwargs) -> str:
    """Get translated string by key. Supports {placeholder} formatting."""
    text = _strings.get(key) or _fallback.get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def current_language() -> str:
    return _current_lang


def available_languages() -> dict:
    """Return dict of available languages (only those with .json files)."""
    result = {}
    if os.path.isdir(LANG_DIR):
        for fname in os.listdir(LANG_DIR):
            if fname.endswith(".json"):
                code = fname[:-5]
                if code in LANGUAGES:
                    result[code] = LANGUAGES[code]
    return result if result else {"en": "English"}
