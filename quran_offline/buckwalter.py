"""Buckwalter <-> Arabic helpers for the Quranic Arabic Corpus morphology file.

The Corpus morphology file uses Buckwalter transliteration in FORM/LEM/ROOT.
This module provides enough round-tripping for Quran study/search UI.
"""

BUCK_TO_AR = {
    "'": "ء", "|": "آ", ">": "أ", "&": "ؤ", "<": "إ", "}": "ئ",
    "A": "ا", "b": "ب", "p": "ة", "t": "ت", "v": "ث", "j": "ج", "H": "ح", "x": "خ",
    "d": "د", "*": "ذ", "r": "ر", "z": "ز", "s": "س", "$": "ش", "S": "ص", "D": "ض",
    "T": "ط", "Z": "ظ", "E": "ع", "g": "غ", "f": "ف", "q": "ق", "k": "ك", "l": "ل",
    "m": "م", "n": "ن", "h": "ه", "w": "و", "Y": "ى", "y": "ي",
    "F": "ً", "N": "ٌ", "K": "ٍ", "a": "َ", "u": "ُ", "i": "ِ", "~": "ّ", "o": "ْ",
    "`": "ٰ", "{": "ٱ", "_": "ـ", "^": "ٓ", "#": "ٔ", ":": "ۜ", "@": "۟", "[": "ۢ", ";": "ۣ", ",": "ۥ", ".": "ۦ", "!": "ۨ", "-": "-", "+": "+",
}
AR_TO_BUCK = {v: k for k, v in BUCK_TO_AR.items()}
# Some Quranic text sources use ordinary alef where Corpus uses alif wasla in lemmas/forms.
AR_TO_BUCK.update({"آ": "|", "أ": ">", "إ": "<", "ا": "A", "ٱ": "{"})

DIACRITICS_AR = set("ًٌٍَُِّْٰۣٓٔۜ۟ۢۥۦۨ")
DIACRITICS_BUCK = set("FNKaui~o`^#:@[;,.!")


def buck_to_ar(text: str | None) -> str:
    if not text:
        return ""
    return "".join(BUCK_TO_AR.get(ch, ch) for ch in text)


def ar_to_buck(text: str | None) -> str:
    if not text:
        return ""
    return "".join(AR_TO_BUCK.get(ch, ch) for ch in text)


def strip_ar_diacritics(text: str | None) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text if ch not in DIACRITICS_AR)


def strip_buck_diacritics(text: str | None) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text if ch not in DIACRITICS_BUCK)


def normalize_query_to_buck(query: str | None) -> str:
    """Accept either Arabic or Buckwalter and return a best-effort Buckwalter value."""
    if not query:
        return ""
    query = query.strip()
    if any("\u0600" <= ch <= "\u06ff" for ch in query):
        return ar_to_buck(query)
    return query
