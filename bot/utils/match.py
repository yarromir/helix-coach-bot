"""нечёткое сопоставление названий (русские склонения и опечатки)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# отбрасываем типичные русские окончания, чтобы сопоставлять основы слов
_ENDINGS = ("ого", "его", "ой", "ая", "ое", "ые", "ый", "ий", "ом", "ам",
            "ах", "ев", "ов", "ы", "и", "а", "е", "у", "ю", "я", "ь")


def _stem(word: str) -> str:
    w = word.lower()
    for end in _ENDINGS:
        if len(w) - len(end) >= 3 and w.endswith(end):
            return w[: -len(end)]
    return w


def _normalize(text: str) -> str:
    words = re.findall(r"\w+", text.lower())
    return " ".join(_stem(w) for w in words)


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"\w+", text.lower())]


def _token_overlap(a_tokens: list[str], b_tokens: list[str]) -> float:
    """доля токенов query, для которых нашёлся близкий токен в кандидате."""
    if not a_tokens:
        return 0.0
    hits = 0
    for ta in a_tokens:
        if any(SequenceMatcher(None, ta, tb).ratio() >= 0.8 for tb in b_tokens):
            hits += 1
    return hits / len(a_tokens)


def similarity(a: str, b: str) -> float:
    seq = SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()
    tok = _token_overlap(_tokens(a), _tokens(b))
    return max(seq, tok)


def fuzzy_find(query: str, candidates: list[str], threshold: float = 0.6) -> str | None:
    """возвращает наиболее похожий вариант из candidates или None.

    учитывает русские склонения (стемминг) и порядок слов (сопоставление токенов).
    """
    best: str | None = None
    best_score = threshold
    qt = _tokens(query)
    nq = " ".join(qt)
    for cand in candidates:
        ct = _tokens(cand)
        nc = " ".join(ct)
        score = SequenceMatcher(None, nq, nc).ratio()
        score = max(score, _token_overlap(qt, ct))
        if nq and nc and (nq in nc or nc in nq):
            score = max(score, 0.85)
        if score >= best_score:
            best_score = score
            best = cand
    return best
