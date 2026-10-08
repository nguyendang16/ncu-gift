"""Server-side translation for every piece of text the API generates itself
(notes, reasons, evidence, capability messages, brief drafts, vocabulary labels).

Design:
  * The language is per request (Accept-Language header, set by ASGI middleware in main.py) and lives in a
    ContextVar, so service code just calls t("key", n=3) without threading a `lang` argument through.
  * Catalogues are plain dicts in app/locales/. English is the source of truth: a key missing from another
    language falls back to English, and tests fail if the catalogues drift apart.
  * Domain vocabulary keyed by an English identifier (purpose.*, dept.*, college.*, project.*) falls back to the
    identifier itself, so unknown data values (a project name from an upload) are shown as they are.
  * Plural: if a key has a "<key>_one" sibling and the language is English, it is used when n == 1.
  * Numbers inside sentences are formatted by the caller, with format specs in the catalogue string, e.g.
    "NT${amount:,.0f}". Static template text must contain no digits (the brief verifier relies on this).
"""
from __future__ import annotations

from contextvars import ContextVar

from .locales import en as _en, zh_TW as _zh

SUPPORTED = ("en", "zh-TW")
DEFAULT = "en"
CATALOGS: dict[str, dict[str, str]] = {"en": _en.M, "zh-TW": _zh.M}

# Keys that exist only to translate an English identifier; English shows the identifier itself.
IDENTIFIER_PREFIXES = ("purpose.", "dept.", "college.", "project.", "item.")

_lang: ContextVar[str] = ContextVar("lang", default=DEFAULT)


def current() -> str:
    return _lang.get()


def set_lang(lang: str):
    return _lang.set(lang if lang in SUPPORTED else DEFAULT)


def reset_lang(token) -> None:
    _lang.reset(token)


def parse_accept_language(header: str | None) -> str:
    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("zh"):
            return "zh-TW"
        if tag.startswith("en"):
            return "en"
    return DEFAULT


def t(key: str, **params) -> str:
    lang = _lang.get()
    cat = CATALOGS[lang]
    msg = None
    if lang == "en" and params.get("n") == 1 and f"{key}_one" in cat:
        msg = cat[f"{key}_one"]
    if msg is None:
        msg = cat.get(key)
    if msg is None:
        msg = CATALOGS["en"][key]          # English fallback; a key absent from English is a bug and raises
    return msg.format(**params) if params else msg


def tr(key: str, default: str) -> str:
    """Translate vocabulary keyed by an English identifier; unknown values are returned unchanged."""
    return CATALOGS[_lang.get()].get(key) or CATALOGS["en"].get(key) or default


# ------------------------------------------------------------ vocabulary labels

def purpose_label(sub: str | None) -> str:
    return tr(f"purpose.{sub}", sub) if sub else ""


def group_label(group: str | None) -> str:
    return t(f"group.{group}") if group else ""


def class_label(cls: str | None) -> str:
    return t(f"class.{cls or 'unknown'}")


def method_label(method: str | None) -> str:
    return t(f"method.{method}") if method else ""


def dept_label(name: str | None) -> str:
    return tr(f"dept.{name}", name) if name else ""


def college_label(name: str | None) -> str:
    return tr(f"college.{name}", name) if name else ""


def project_label(name: str | None) -> str:
    return tr(f"project.{name}", name) if name else ""


def field_label(key: str) -> str:
    return t(f"field.{key}")


_MOCK_PREFIXES = {"Mock Donor": "mock.donor", "Mock Corp.": "mock.corp", "Mock Foundation": "mock.foundation"}


def donor_name_label(name: str) -> str:
    """Display names in the synthetic dataset are English placeholders; show them in the active language."""
    for prefix, key in _MOCK_PREFIXES.items():
        if name.startswith(prefix):
            return t(key) + name[len(prefix):]
    return name


def target_label(kind: str, name: str) -> str:
    return {"sub": purpose_label, "unit": dept_label, "project": project_label}[kind](name)


_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def month_label(m: int) -> str:
    return f"{m}月" if _lang.get() == "zh-TW" else _EN_MONTHS[m - 1]
