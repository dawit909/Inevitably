from .base import BaseLangParser
from .en import EnglishParser
from .ko import KoreanParser

# Static registry keeps PyInstaller bundling automatic with no hidden-import flags.
# To add a new language later (e.g. Russian or Japanese), add langs/ru.py and register it here.
PARSERS: dict[str, BaseLangParser] = {
    "en": EnglishParser(),
    "ko": KoreanParser(),
}


def detect_language(enemies: list[dict]) -> str:
    sample = "".join(e.get("champ_display", "") for e in enemies)
    if any("\uac00" <= ch <= "\ud7a3" for ch in sample):
        return "ko"
    if any("\u0400" <= ch <= "\u04ff" for ch in sample):
        return "ru"
    if any("\u3040" <= ch <= "\u30ff" for ch in sample):
        return "ja"
    if any("\u4e00" <= ch <= "\u9fff" for ch in sample):
        return "zh"
    return "en"


def get_parser(lang_code: str) -> BaseLangParser:
    return PARSERS.get(lang_code, PARSERS["en"])
