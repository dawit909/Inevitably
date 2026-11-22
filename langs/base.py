import difflib
import re
import unicodedata

_OCR_DEBUG_NOISE_RE = re.compile(r"(?:\[OCR|enemy=|col=|ts=)", re.IGNORECASE)
_SENDER_PAREN_RE = re.compile(r"^(.*?\))\s*(?:[:;.,'\"•·]|[^\w\s])?\s*(.*)$")
_TS_COLON_RE = re.compile(r"^\s*(\d{1,2})\s*[:.;•·]\s*(\d{2})(?:\D|$)")
_TS_FIVE_DIGIT_RE = re.compile(r"^\s*(\d{2})1(\d{2})(?:\D|$)")
_TS_COMPACT_RE = re.compile(r"^\s*(\d{2})(\d{2})(?:\s|$)")
_K_GLITCH_RE = re.compile(r"(?:[lI|1f]<)")
_TRAILING_NOISE_RE = re.compile(r"[\s.,;:'\"`~•·\-–—_/?*!|]+$")


def preclean_ocr(text: str) -> str:
    """Normalize Unicode lookalikes (e.g. 'Ⅵ' -> 'VI') and common glyph splits."""
    s = unicodedata.normalize("NFKC", text or "")
    s = _K_GLITCH_RE.sub("k", s)
    return s.strip()


def norm_latin_token(text: str) -> str:
    s = preclean_ocr(text).lower()
    s = s.replace("|", "i").replace("l", "i").replace("1", "i")
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE)


def extract_timestamp(prefix: str) -> int | None:
    """Recover [MM:SS] from the start of a chat sender prefix even with OCR digit glitches."""
    if not prefix:
        return None
    head = re.sub(r"^[\s~•·.\-\[\(\"'`]+", "", prefix)
    if head.startswith("이") and len(head) >= 2 and head[1] in ":.;•· 0123456789|lI":
        head = "01" + head[1:]
    m_word = re.search(r"[A-Za-z\u0400-\u04ff\uac00-\ud7a3]{2,}", head)
    zone = head[: m_word.start()] if m_word else head[:12]
    zone = re.sub(r"[|lI\]\[]", "1", zone)
    zone = re.sub(r"[Oo]", "0", zone)
    zone = re.sub(r"\s*([:.;•·])\s*", ":", zone)
    zone = re.sub(r"(?<=\d)\s+(?=\d)", "", zone)

    m = _TS_COLON_RE.match(zone) or _TS_FIVE_DIGIT_RE.match(zone) or _TS_COMPACT_RE.match(zone)
    if not m:
        return None
    mins, secs = int(m.group(1)), int(m.group(2))
    if mins <= 99 and secs < 60:
        return mins * 60 + secs
    return None


def split_sender_and_body(text: str) -> tuple[str, str]:
    """Split '[MM:SS] Player (Champ): Body' using the LAST ')' or ':' so timestamp colons never interfere."""
    m = _SENDER_PAREN_RE.match(text)
    if m and m.group(2).strip():
        return m.group(1), m.group(2).strip()

    rcolon = text.rfind(":")
    if rcolon >= 4:
        return text[:rcolon], text[rcolon + 1:].strip()

    return "", text.strip()


def trim_trailing_noise(text: str) -> str:
    return _TRAILING_NOISE_RE.sub("", text).strip()


class BaseLangParser:
    code: str = "en"
    preferred_ocr_tags: tuple[str, ...] = ("en-US", "en-GB")
    ready_or_cd_re: re.Pattern = re.compile(r"(?:\bready\b|\d+\s*s\b|\d+:\d{2})", re.IGNORECASE)
    ult_tokens: set[str] = {"r", "ult", "ultimate"}

    def extra_spell_aliases(self, spell: dict) -> list[str]:
        return []

    def preprocess_lines(self, raw_lines: list[str]) -> list[str]:
        """Stitch split lines where OCR puts '01:20 Player (Champ):' on one line and the ping on the next."""
        merged: list[str] = []
        i = 0
        while i < len(raw_lines):
            cur = raw_lines[i].strip()
            if not cur:
                i += 1
                continue
            if (
                i + 1 < len(raw_lines)
                and re.search(r"\)\s*[:;.]?\s*$", cur)
                and ")" not in raw_lines[i + 1]
                and not _TS_COLON_RE.match(raw_lines[i + 1])
            ):
                nxt = raw_lines[i + 1].strip()
                if nxt:
                    merged.append(f"{cur} {nxt}")
                    i += 2
                    continue
            merged.append(cur)
            i += 1
        return merged

    def fuzzy_score(self, candidate: str, target: str) -> float:
        c = norm_latin_token(candidate)
        t = norm_latin_token(target)
        if not c or not t:
            return 0.0
        if c == t:
            return 1.0
        if len(t) <= 3 or len(c) <= 3:
            return 0.0
        return difflib.SequenceMatcher(None, c, t).ratio()

    def spell_targets_for_enemy(self, enemy: dict, ult_names: dict[str, str]) -> list[tuple[int, str]]:
        targets: list[tuple[int, str]] = []
        for slot in (0, 1):
            sp = enemy["spells"][slot]
            for t in (sp.get("display_name", ""), sp.get("en_name", "")):
                if t:
                    targets.append((slot, t))
            for alias in self.extra_spell_aliases(sp):
                targets.append((slot, alias))
        for tok in self.ult_tokens:
            targets.append((2, tok))
        uname = ult_names.get(enemy["champ_id"], "")
        if uname:
            targets.append((2, uname))
        return targets

    def match_enemy(
        self,
        left_clean: str,
        enemies: list[dict],
        require_same_word_count: bool = False,
    ) -> tuple[dict | None, float]:
        left_words = [w for w in re.split(r"\s+", left_clean) if w]
        best_enemy = None
        best_score = 0.0
        for enemy in enemies:
            for cand in (enemy.get("champ_display", ""), enemy.get("champ_id", "")):
                if not cand:
                    continue
                if require_same_word_count:
                    cand_words = [w for w in re.split(r"\s+", cand) if w]
                    if len(left_words) != len(cand_words):
                        continue
                score = self.fuzzy_score(left_clean, cand)
                if score > best_score:
                    best_score = score
                    best_enemy = enemy
        return best_enemy, best_score

    def match_spell(
        self,
        right_clean: str,
        enemy: dict,
        ult_names: dict[str, str],
    ) -> tuple[int | None, float]:
        best_col: int | None = None
        best_score = 0.0
        rn = norm_latin_token(right_clean)

        for col, target in self.spell_targets_for_enemy(enemy, ult_names):
            if col == 2 and target in self.ult_tokens:
                score = 1.0 if rn == norm_latin_token(target) else 0.0
            else:
                score = self.fuzzy_score(right_clean, target)
            if score > best_score:
                best_score = score
                best_col = col
        return best_col, best_score

    def parse_body(
        self,
        body_clean: str,
        enemies: list[dict],
        ult_names: dict[str, str],
    ) -> tuple[str, int] | None:
        raise NotImplementedError

    def parse_line(
        self,
        line: str,
        enemies: list[dict],
        ult_names: dict[str, str],
    ) -> tuple[str, int, int | None] | None:
        raw = (line or "").strip()
        if len(raw) < 4 or _OCR_DEBUG_NOISE_RE.search(raw):
            return None

        text = preclean_ocr(raw)
        sender_part, body = split_sender_and_body(text)
        if not body:
            return None

        msg_ts = extract_timestamp(sender_part) if sender_part else extract_timestamp(text)
        if self.ready_or_cd_re.search(body):
            return None

        body_clean = trim_trailing_noise(body)
        if not body_clean:
            return None

        res = self.parse_body(body_clean, enemies, ult_names)
        if res is None:
            return None
        return res[0], res[1], msg_ts
