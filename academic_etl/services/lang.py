"""Language heuristics for the English-only catalog.

`is_english(text)` decides whether a short field value is English. Beyondegree is
a worldwide catalog normalized to one language, so non-English values (e.g.
Vietnamese "Đại học Bách khoa Hà Nội", or CJK) are flagged in validation and
excluded from the CSV export. The check is a cheap character heuristic — no
network, no model.
"""

import re

# CJK / Hangul / Hiragana / Katakana ranges -> definitely not English.
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")

# Above this share of accented (non-ASCII) letters, treat as non-English. A
# stray diacritic in a proper noun (e.g. "Đà Nẵng University of Technology")
# stays under the bar; a Vietnamese phrase blows past it.
_NON_ASCII_LETTER_RATIO = 0.15


def is_english(text) -> bool:
    if not text:
        return True  # empty is not a violation
    s = str(text)
    if _CJK_RE.search(s):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return True  # numbers/punctuation only (e.g. "4 years", "VND 30,000")
    non_ascii = sum(1 for c in letters if ord(c) > 127)
    return (non_ascii / len(letters)) <= _NON_ASCII_LETTER_RATIO
