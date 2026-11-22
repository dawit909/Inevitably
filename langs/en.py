import re

from .base import BaseLangParser, norm_latin_token, trim_trailing_noise

_PING_SPLIT_RE = re.compile(r"\s*(?:[-–—~=_•·]+|\bused\b|\bcast\b)\s*", re.IGNORECASE)


class EnglishParser(BaseLangParser):
    code = "en"
    preferred_ocr_tags = ("en-US", "en-GB")
    ready_or_cd_re = re.compile(r"(?:\bready\b|\d+\s*s\b|\d+:\d{2})", re.IGNORECASE)
    ult_tokens = {"r", "ult", "ultimate"}

    def extra_spell_aliases(self, spell: dict) -> list[str]:
        if spell.get("key") == "SummonerTeleport":
            return ["Unleashed Teleport"]
        return []

    def parse_body(
        self,
        body_clean: str,
        enemies: list[dict],
        ult_names: dict[str, str],
    ) -> tuple[str, int] | None:
        # Pattern 1: Explicit separator ('Malphite used Flash', 'Nami - Flash')
        parts = _PING_SPLIT_RE.split(body_clean, maxsplit=1)
        if len(parts) == 2:
            left_clean = re.sub(r"\([^)]*\)", "", parts[0]).strip()
            right_clean = re.split(r"[-–—|]", parts[1], maxsplit=1)[0].strip()
            right_clean = trim_trailing_noise(right_clean)
            if left_clean and right_clean:
                enemy, c_score = self.match_enemy(left_clean, enemies, require_same_word_count=False)
                if enemy is not None and c_score >= 0.78:
                    col, s_score = self.match_spell(right_clean, enemy, ult_names)
                    if col is not None and s_score >= 0.78:
                        return enemy["id"], col

        # Pattern 2: Direct scoreboard ping ('Gragas Flash', 'Ziggs Teleport', 'Renata Glasc Heal')
        words = [w for w in re.split(r"\s+", body_clean) if w]
        if len(words) >= 2:
            best_hit: tuple[str, int, float] | None = None
            for enemy in enemies:
                for col, target in self.spell_targets_for_enemy(enemy, ult_names):
                    t_words = [w for w in re.split(r"\s+", target) if w]
                    k = len(t_words)
                    if k == 0 or len(words) <= k:
                        continue
                    left_str = " ".join(words[:-k])
                    right_str = " ".join(words[-k:])
                    if col == 2 and target in self.ult_tokens:
                        s_score = 1.0 if norm_latin_token(right_str) == norm_latin_token(target) else 0.0
                    else:
                        s_score = self.fuzzy_score(right_str, target)
                    if s_score < 0.80:
                        continue
                    matched_enemy, c_score = self.match_enemy(left_str, [enemy], require_same_word_count=True)
                    if matched_enemy is not None and c_score >= 0.80:
                        combined = c_score + s_score
                        if best_hit is None or combined > best_hit[2]:
                            best_hit = (enemy["id"], col, combined)
            if best_hit is not None:
                return best_hit[0], best_hit[1]

        return None
