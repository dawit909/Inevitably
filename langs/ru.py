import difflib
import re

from .base import BaseLangParser, norm_latin_token, preclean_ocr, trim_trailing_noise

_DASH_SPLIT_RE = re.compile(r"\s*[-–—~=_•·]+\s*")
_GUILLEMET_RE = re.compile(r"[«»\"']")

_USED_VERBS = (
    "применяет",
    "применил",
    "применила",
    "использует",
    "использовал",
    "использовала",
)

# Fold common Latin lookalikes and dropped diacritics produced by Russian OCR on game fonts
_CYR_NORM_TABLE = str.maketrans(
    {
        "a": "а",
        "b": "в",
        "c": "с",
        "e": "е",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "t": "т",
        "x": "х",
        "y": "у",
        "0": "о",
        "3": "з",
        "6": "б",
        "ё": "е",
        "й": "и",
        "ъ": "ь",
        "і": "и",
        "ї": "и",
    }
)


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def _norm_cyrillic(text: str) -> str:
    s = preclean_ocr(text).lower().translate(_CYR_NORM_TABLE)
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE)


class RussianParser(BaseLangParser):
    code = "ru"
    preferred_ocr_tags = ("ru", "ru-RU")
    ready_or_cd_re = re.compile(
        r"(?:\bready\b|\d+\s*(?:s|с|сек)\b|\d+:\d{2}|готов|осталось)",
        re.IGNORECASE,
    )
    ult_tokens = {"r", "ult", "ульт", "ульта", "ультимейт"}

    def extra_spell_aliases(self, spell: dict) -> list[str]:
        if spell.get("key") == "SummonerTeleport":
            return ["Усиленный телепорт", "Телепорт"]
        return []

    def fuzzy_score(self, candidate: str, target: str) -> float:
        if _has_cyrillic(target):
            c = _norm_cyrillic(candidate)
            t = _norm_cyrillic(target)
            if not c or not t:
                return 0.0
            if c == t:
                return 1.0
            # Allow a 1-char OCR typo on 4-letter Russian spells/champions (Кара, Люкс, Нами, Джин, etc.)
            if len(c) == 4 and len(t) == 4:
                ratio = difflib.SequenceMatcher(None, c, t).ratio()
                return 0.80 if ratio >= 0.75 else 0.0
            if len(t) <= 3 or len(c) <= 3:
                return 0.0
            return difflib.SequenceMatcher(None, c, t).ratio()

        return super().fuzzy_score(candidate, target)

    def _is_ult_token_match(self, candidate: str, token: str) -> bool:
        if _has_cyrillic(token):
            return _norm_cyrillic(candidate) == _norm_cyrillic(token)
        return norm_latin_token(candidate) == norm_latin_token(token)

    def match_spell(
        self,
        right_clean: str,
        enemy: dict,
        ult_names: dict[str, str],
    ) -> tuple[int | None, float]:
        best_col: int | None = None
        best_score = 0.0

        for col, target in self.spell_targets_for_enemy(enemy, ult_names):
            if col == 2 and target in self.ult_tokens:
                score = 1.0 if self._is_ult_token_match(right_clean, target) else 0.0
            else:
                score = self.fuzzy_score(right_clean, target)
            if score > best_score:
                best_score = score
                best_col = col
        return best_col, best_score

    @staticmethod
    def _is_used_verb(word: str) -> bool:
        w = _norm_cyrillic(word)
        if len(w) < 6:
            return False
        return any(difflib.SequenceMatcher(None, w, v).ratio() >= 0.74 for v in _USED_VERBS)

    @staticmethod
    def _matches_champ_word_count(left_words: list[str], champ_cand: str) -> bool:
        space_cnt = len([w for w in re.split(r"\s+", champ_cand) if w])
        punct_cnt = len([w for w in re.split(r"[\s'\-]+", champ_cand) if w])
        lo = min(space_cnt, punct_cnt)
        hi = max(space_cnt, punct_cnt)
        return lo <= len(left_words) <= hi

    def parse_body(
        self,
        body_clean: str,
        enemies: list[dict],
        ult_names: dict[str, str],
    ) -> tuple[str, int] | None:
        cleaned = _GUILLEMET_RE.sub("", body_clean).strip()
        if not cleaned:
            return None

        words = [w for w in re.split(r"\s+", cleaned) if w]

        # Pattern 1: '<Champion> применяет <Spell>' (also handles OCR typos in the verb)
        if len(words) >= 3:
            for idx in range(1, len(words) - 1):
                if not self._is_used_verb(words[idx]):
                    continue
                left_clean = re.sub(r"\([^)]*\)", "", " ".join(words[:idx])).strip()
                right_clean = trim_trailing_noise(" ".join(words[idx + 1 :]))
                if left_clean and right_clean:
                    enemy, c_score = self.match_enemy(left_clean, enemies, require_same_word_count=False)
                    if enemy is not None and c_score >= 0.78:
                        col, s_score = self.match_spell(right_clean, enemy, ult_names)
                        if col is not None and s_score >= 0.78:
                            return enemy["id"], col

        # Pattern 2: Dash separator ('Диана - Скачок')
        dash_parts = _DASH_SPLIT_RE.split(cleaned, maxsplit=1)
        if len(dash_parts) == 2:
            left_clean = re.sub(r"\([^)]*\)", "", dash_parts[0]).strip()
            right_clean = trim_trailing_noise(dash_parts[1])
            if left_clean and right_clean:
                enemy, c_score = self.match_enemy(left_clean, enemies, require_same_word_count=False)
                if enemy is not None and c_score >= 0.78:
                    col, s_score = self.match_spell(right_clean, enemy, ult_names)
                    if col is not None and s_score >= 0.78:
                        return enemy["id"], col

        # Pattern 3: Direct scoreboard ping ('Диана Скачок', 'Рената Гласк Исцеление', 'Вел'Коз Скачок')
        if len(words) >= 2:
            best_hit: tuple[str, int, float] | None = None
            for enemy in enemies:
                champ_cands = [c for c in (enemy.get("champ_display", ""), enemy.get("champ_id", "")) if c]
                for col, target in self.spell_targets_for_enemy(enemy, ult_names):
                    t_words = [w for w in re.split(r"\s+", target) if w]
                    k = len(t_words)
                    if k == 0 or len(words) <= k:
                        continue
                    left_words = words[:-k]
                    right_str = " ".join(words[-k:])

                    if col == 2 and target in self.ult_tokens:
                        s_score = 1.0 if self._is_ult_token_match(right_str, target) else 0.0
                    else:
                        s_score = self.fuzzy_score(right_str, target)
                    if s_score < 0.80:
                        continue

                    left_str = " ".join(left_words)
                    c_score = max(
                        (
                            self.fuzzy_score(left_str, cand)
                            for cand in champ_cands
                            if self._matches_champ_word_count(left_words, cand)
                        ),
                        default=0.0,
                    )
                    if c_score >= 0.80:
                        combined = c_score + s_score
                        if best_hit is None or combined > best_hit[2]:
                            best_hit = (enemy["id"], col, combined)

            if best_hit is not None:
                return best_hit[0], best_hit[1]

        return None