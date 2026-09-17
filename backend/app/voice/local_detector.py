import logging

from app.voice.language import (
    LanguageDetectionResult,
    LanguageDetector,
    LanguageLabel,
)

_DEVANAGARI_RANGES: tuple[tuple[int, int], ...] = ((0x0900, 0x097F),)
_ARABIC_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)
_LATIN_RANGES: tuple[tuple[int, int], ...] = (
    (0x0041, 0x005A),
    (0x0061, 0x007A),
    (0x00C0, 0x024F),
)

_ENGLISH_WORDS = frozenset(
    {
        "a",
        "about",
        "actually",
        "also",
        "am",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "but",
        "by",
        "can",
        "check",
        "code",
        "could",
        "did",
        "do",
        "does",
        "each",
        "english",
        "even",
        "every",
        "exam",
        "explain",
        "for",
        "from",
        "get",
        "going",
        "had",
        "happen",
        "happening",
        "has",
        "have",
        "hello",
        "help",
        "hey",
        "hi",
        "how",
        "important",
        "into",
        "is",
        "it",
        "just",
        "laptop",
        "like",
        "make",
        "me",
        "more",
        "most",
        "my",
        "no",
        "not",
        "now",
        "of",
        "on",
        "one",
        "open",
        "or",
        "other",
        "our",
        "please",
        "project",
        "question",
        "simply",
        "slow",
        "some",
        "than",
        "that",
        "the",
        "their",
        "them",
        "these",
        "they",
        "this",
        "time",
        "to",
        "today",
        "topics",
        "up",
        "us",
        "use",
        "very",
        "vs",
        "was",
        "we",
        "weather",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "work",
        "would",
        "you",
        "your",
    }
)

_HINGLISH_WORDS = frozenset(
    {
        "aa",
        "aaj",
        "aap",
        "ab",
        "abhi",
        "accha",
        "achha",
        "achhe",
        "agar",
        "aisa",
        "aise",
        "andar",
        "aur",
        "baat",
        "bahut",
        "batao",
        "behen",
        "beta",
        "bhai",
        "chahiye",
        "chahta",
        "chala",
        "chalo",
        "de",
        "dekh",
        "dekho",
        "dekhna",
        "dene",
        "dikha",
        "dikhao",
        "din",
        "diya",
        "fikar",
        "gaya",
        "gayi",
        "ha",
        "hai",
        "hain",
        "hamein",
        "hamesha",
        "ho",
        "hoga",
        "hona",
        "hu",
        "hum",
        "humko",
        "jaa",
        "jaata",
        "jab",
        "jaise",
        "jao",
        "ka",
        "kaam",
        "kab",
        "kahan",
        "kaisa",
        "kaise",
        "kal",
        "kam",
        "kar",
        "karna",
        "karo",
        "karte",
        "karti",
        "kya",
        "lekar",
        "log",
        "maaf",
        "main",
        "maine",
        "mat",
        "mein",
        "mera",
        "mere",
        "meri",
        "mujhe",
        "muze",
        "na",
        "nahi",
        "naam",
        "namaste",
        "namaskar",
        "paani",
        "par",
        "phir",
        "raat",
        "raha",
        "rahi",
        "raho",
        "sab",
        "sahi",
        "samajh",
        "samajhte",
        "samjho",
        "se",
        "sirf",
        "shukriya",
        "thik",
        "tujhe",
        "tum",
        "tumhara",
        "tumhari",
        "waala",
        "waali",
        "wala",
        "wale",
        "wo",
        "woh",
        "yaar",
        "yahan",
        "yahi",
        "ye",
        "yeh",
    }
)


def _in_ranges(char: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in ranges)


class LocalLanguageDetector(LanguageDetector):
    """Deterministic, offline language detector for English/Hindi/Urdu.

    The detector inspects character scripts and a small legacy keyword
    vocabulary. It is intentionally conservative: it never claims perfect
    identification and returns ``unknown`` (without a confidence) whenever it
    has no defensible answer. Confidence is only produced when script or
    vocabulary evidence justifies it.
    """

    name = "local-language-detector"
    description = "Deterministic offline detector for English, Hindi, Hinglish, and Urdu."

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    async def detect(self, text: str) -> LanguageDetectionResult:
        devanagari = self._count_script(text or "", _DEVANAGARI_RANGES)
        arabic = self._count_script(text or "", _ARABIC_RANGES)
        latin = self._count_script(text or "", _LATIN_RANGES)
        english_hits, hinglish_hits = self._vocab_hits(text or "")
        total_script = devanagari + arabic + latin

        if total_script == 0:
            result = LanguageDetectionResult.unknown()
        elif devanagari and arabic:
            result = self._script_pair(devanagari, arabic, total_script)
        elif devanagari and latin:
            result = self._dev_latin_pair(
                devanagari, latin, english_hits, hinglish_hits, total_script
            )
        elif arabic and latin:
            result = self._ara_latin_pair(arabic, latin, english_hits, hinglish_hits, total_script)
        elif devanagari:
            result = LanguageDetectionResult.detected(
                LanguageLabel.HINDI, confidence=0.95, languages=(LanguageLabel.HINDI,)
            )
        elif arabic:
            result = LanguageDetectionResult.detected(
                LanguageLabel.URDU, confidence=0.9, languages=(LanguageLabel.URDU,)
            )
        else:
            result = self._latin_only(english_hits, hinglish_hits, latin)

        self._logger.info(
            "Detected language label=%s confidence=%s is_mixed=%s",
            result.label.value,
            result.confidence,
            result.is_mixed,
        )
        return result

    @staticmethod
    def _count_script(text: str, ranges: tuple[tuple[int, int], ...]) -> int:
        return sum(1 for char in text if _in_ranges(char, ranges))

    @staticmethod
    def _vocab_hits(text: str) -> tuple[int, int]:
        english_hits = 0
        hinglish_hits = 0
        for token in text.split():
            word = "".join(char for char in token if char.isalnum()).lower()
            if not word:
                continue
            if word in _ENGLISH_WORDS:
                english_hits += 1
            if word in _HINGLISH_WORDS:
                hinglish_hits += 1
        return english_hits, hinglish_hits

    def _script_pair(
        self,
        devanagari: int,
        arabic: int,
        total_script: int,
    ) -> LanguageDetectionResult:
        devanagari_ratio = devanagari / total_script
        arabic_ratio = arabic / total_script
        if devanagari_ratio >= 0.25 and arabic_ratio >= 0.25:
            return LanguageDetectionResult.mixed(LanguageLabel.HINDI, LanguageLabel.URDU)
        if devanagari_ratio >= arabic_ratio:
            return LanguageDetectionResult.detected(
                LanguageLabel.HINDI, confidence=0.95, languages=(LanguageLabel.HINDI,)
            )
        return LanguageDetectionResult.detected(
            LanguageLabel.URDU, confidence=0.9, languages=(LanguageLabel.URDU,)
        )

    def _dev_latin_pair(
        self,
        devanagari: int,
        latin: int,
        english_hits: int,
        hinglish_hits: int,
        total_script: int,
    ) -> LanguageDetectionResult:
        devanagari_ratio = devanagari / total_script
        latin_ratio = latin / total_script
        if devanagari_ratio >= 0.30 and latin_ratio >= 0.30:
            return LanguageDetectionResult.mixed(LanguageLabel.HINDI, LanguageLabel.ENGLISH)
        if devanagari_ratio >= 0.30 and devanagari >= latin:
            return LanguageDetectionResult.detected(
                LanguageLabel.HINDI, confidence=0.95, languages=(LanguageLabel.HINDI,)
            )
        return self._latin_only(english_hits, hinglish_hits, latin)

    def _ara_latin_pair(
        self,
        arabic: int,
        latin: int,
        english_hits: int,
        hinglish_hits: int,
        total_script: int,
    ) -> LanguageDetectionResult:
        arabic_ratio = arabic / total_script
        latin_ratio = latin / total_script
        if arabic_ratio >= 0.30 and latin_ratio >= 0.30:
            return LanguageDetectionResult.mixed(LanguageLabel.URDU, LanguageLabel.ENGLISH)
        if arabic_ratio >= 0.30 and arabic >= latin:
            return LanguageDetectionResult.detected(
                LanguageLabel.URDU, confidence=0.9, languages=(LanguageLabel.URDU,)
            )
        return self._latin_only(english_hits, hinglish_hits, latin)

    def _latin_only(
        self, english_hits: int, hinglish_hits: int, latin: int
    ) -> LanguageDetectionResult:
        if latin == 0 or (english_hits == 0 and hinglish_hits == 0):
            return LanguageDetectionResult.unknown()

        if hinglish_hits > english_hits or (
            hinglish_hits >= 2 and 2 * hinglish_hits >= english_hits
        ):
            label = LanguageLabel.HINGLISH
            dominant = hinglish_hits
        else:
            label = LanguageLabel.ENGLISH
            dominant = english_hits
        confidence = round(min(0.85, 0.5 + 0.35 * dominant / (english_hits + hinglish_hits)), 2)
        return LanguageDetectionResult.detected(label, confidence=confidence, languages=(label,))
