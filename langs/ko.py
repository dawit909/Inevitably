import difflib
import re
import unicodedata

from .base import BaseLangParser, norm_latin_token, preclean_ocr, trim_trailing_noise

_KO_NIMI_SPLIT_RE = re.compile(
    r"[\s.,;:'\"`~•·\-–—_“”]*님\s*(?:[이의][\s.,;:'\"`~•·\-–—_“”]*|[\s.,;:'\"`~•·\-–—_“”]+)"
)
_KO_SAYONG_TAIL_RE = re.compile(
    r"(?:[\s』」\])]+(?:사\S*|[A-Za-z0-9]{1,3}용\S*).*$|[\s』」\])]*사\s*[용횽응웅요공구듣를수亏올훌~。]\S*.*$)"
)
_DASH_SPLIT_RE = re.compile(r"\s*[-–—~=_•·]+\s*")


def _has_hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def _is_pure_hangul(text: str) -> bool:
    return bool(text) and all("\uac00" <= ch <= "\ud7a3" for ch in text)


def _to_jamo_norm(text: str) -> str:
    s = unicodedata.normalize("NFD", preclean_ocr(text).lower())
    return re.sub(r"[^\w\u1100-\u11ff\u3131-\u318e]", "", s, flags=re.UNICODE)


class KoreanParser(BaseLangParser):
    code = "ko"
    preferred_ocr_tags = ("ko", "ko-KR")
    ready_or_cd_re = re.compile(r"(?:\bready\b|\d+\s*s\b|\d+:\d{2}|준비|남음|\d+\s*초)", re.IGNORECASE)
    ult_tokens = {"r", "ult", "궁", "궁극기"}

    def extra_spell_aliases(self, spell: dict) -> list[str]:
        if spell.get("key") == "SummonerTeleport":
            return ["풀려난 순간이동", "순간이동"]
        return []

    def fuzzy_score(self, candidate: str, target: str) -> float:
        if _has_hangul(target) or _has_hangul(candidate):
            t_raw = re.sub(r"[^\uac00-\ud7a3A-Za-z0-9]", "", preclean_ocr(target)).lower()
            c_raw = re.sub(r"[^\uac00-\ud7a3A-Za-z0-9]", "", preclean_ocr(candidate)).lower()
            if not c_raw or not t_raw:
                return 0.0

            # Strip 1-2 stray Latin/digit OCR artifacts on pure-Hangul targets (e.g. '가런l' -> '가런')
            if _is_pure_hangul(t_raw):
                c_ko = re.sub(r"[^\uac00-\ud7a3]", "", c_raw)
                if c_ko and (len(c_raw) - len(c_ko)) <= 2 and len(c_ko) >= len(t_raw) - 1:
                    c_raw = c_ko

            if c_raw == t_raw:
                return 1.0
            c = _to_jamo_norm(c_raw)
            t = _to_jamo_norm(t_raw)
            if not c or not t:
                return 0.0
            if c == t:
                return 1.0

            # Allow 1-jamo OCR typo on 2-syllable no-받침 champion names (티모->리모, 나미, 아리, etc.)
            if len(c_raw) == 2 and len(t_raw) == 2 and len(c) == 4 and len(t) == 4:
                ratio = difflib.SequenceMatcher(None, c, t).ratio()
                return 0.80 if ratio >= 0.75 else 0.0

            if len(t) < 5 or len(c) < 5:
                return 0.0
            return difflib.SequenceMatcher(None, c, t).ratio()

        return super().fuzzy_score(candidate, target)

    def _match_compact(
        self,
        body_clean: str,
        enemies: list[dict],
        ult_names: dict[str, str],
        allow_honorific_suffix: bool = False,
    ) -> tuple[str, int] | None:
        compact = re.sub(r"[^\uac00-\ud7a3A-Za-z]", "", preclean_ocr(body_clean))
        if len(compact) < 3:
            return None

        best_hit: tuple[str, int, float] | None = None
        for enemy in enemies:
            champ_cands = [
                re.sub(r"[^\uac00-\ud7a3A-Za-z]", "", preclean_ocr(c))
                for c in (enemy.get("champ_display", ""), enemy.get("champ_id", ""))
                if c and _has_hangul(c)
            ]
            if not champ_cands:
                continue

            for col, target in self.spell_targets_for_enemy(enemy, ult_names):
                if not (_has_hangul(target) or target.lower() == "r"):
                    continue
                t_comp = re.sub(r"[^\uac00-\ud7a3A-Za-z]", "", preclean_ocr(target))
                ls = len(t_comp)
                if ls == 0 or len(compact) <= ls:
                    continue

                right_str = compact[-ls:]
                if col == 2 and target in self.ult_tokens:
                    s_score = 1.0 if norm_latin_token(right_str) == norm_latin_token(target) else 0.0
                else:
                    s_score = self.fuzzy_score(right_str, t_comp)
                if s_score < 0.78:
                    continue

                prefix = compact[:-ls]
                prefix_variants = [prefix]
                if allow_honorific_suffix and prefix.endswith("이"):
                    if len(prefix) >= 3:
                        prefix_variants.append(prefix[:-2])
                    if len(prefix) >= 2:
                        prefix_variants.append(prefix[:-1])

                for cand_champ in champ_cands:
                    lc = len(cand_champ)
                    max_len_diff = 1 if lc >= 4 else 0
                    pure_ko_champ = _is_pure_hangul(cand_champ)
                    for pv in prefix_variants:
                        if not pv:
                            continue
                        if pure_ko_champ:
                            pv_ko = re.sub(r"[^\uac00-\ud7a3]", "", pv)
                            if pv_ko and (len(pv) - len(pv_ko)) <= 2:
                                pv = pv_ko
                        if abs(len(pv) - lc) > max_len_diff:
                            continue
                        c_score = self.fuzzy_score(pv, cand_champ)
                        if c_score >= 0.78:
                            combined = c_score + s_score
                            if best_hit is None or combined > best_hit[2]:
                                best_hit = (enemy["id"], col, combined)

        if best_hit is not None:
            return best_hit[0], best_hit[1]
        return None

    def parse_body(
        self,
        body_clean: str,
        enemies: list[dict],
        ult_names: dict[str, str],
    ) -> tuple[str, int] | None:
        # Pattern 1: '<Champion> 님이/님의/님 <Spell> 사용'
        ko_parts = _KO_NIMI_SPLIT_RE.split(body_clean, maxsplit=1)
        if len(ko_parts) == 2:
            left_clean = re.sub(r"\([^)]*\)", "", ko_parts[0]).strip()
            right_raw = _KO_SAYONG_TAIL_RE.sub("", ko_parts[1]).strip()
            right_clean = trim_trailing_noise(right_raw)
            if left_clean and right_clean:
                enemy, c_score = self.match_enemy(left_clean, enemies, require_same_word_count=False)
                if enemy is not None and c_score >= 0.78:
                    col, s_score = self.match_spell(right_clean, enemy, ult_names)
                    if col is not None and s_score >= 0.78:
                        return enemy["id"], col

        # Pattern 1b: Garbled '님이' (e.g. '베이가뇜이 점멸 사~') when ending in a '사용' tail
        m_sayong = _KO_SAYONG_TAIL_RE.search(body_clean)
        if m_sayong:
            inner = body_clean[: m_sayong.start()].strip()
            hit = self._match_compact(inner, enemies, ult_names, allow_honorific_suffix=True)
            if hit is not None:
                return hit

        # Pattern 2: Dash separator ('오공 - 점멸')
        dash_parts = _DASH_SPLIT_RE.split(body_clean, maxsplit=1)
        if len(dash_parts) == 2:
            left_clean = re.sub(r"\([^)]*\)", "", dash_parts[0]).strip()
            right_clean = trim_trailing_noise(dash_parts[1])
            if left_clean and right_clean:
                enemy, c_score = self.match_enemy(left_clean, enemies, require_same_word_count=False)
                if enemy is not None and c_score >= 0.78:
                    col, s_score = self.match_spell(right_clean, enemy, ult_names)
                    if col is not None and s_score >= 0.78:
                        return enemy["id"], col

        # Pattern 3: Direct scoreboard ping ('오공 강타', '트린 다미어 점멸', '가런l 점화', '리모 점멸')
        return self._match_compact(body_clean, enemies, ult_names, allow_honorific_suffix=False)