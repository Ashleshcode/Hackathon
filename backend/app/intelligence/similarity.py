"""Caption and URL comparison. Lightweight and CPU only."""

import re
from urllib.parse import urlsplit, urlunsplit

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
WORD_PATTERN = re.compile(r"(?u)\b\w\w+\b")

# Very short captions ("so true!") match by chance, so they are never compared.
MIN_CONTENT_WORDS = 4


def _content_word_count(text: str) -> int:
    return sum(1 for word in WORD_PATTERN.findall(text.lower()) if word not in ENGLISH_STOP_WORDS)


def similar_caption_pairs(texts: list[str | None], threshold: float) -> dict[tuple[int, int], float]:
    """Returns {(i, j): cosine similarity} for i < j at or above the threshold."""
    # URLs are removed first: they have their own signal, and the words inside a
    # shared link would otherwise count a second time as caption similarity.
    captions = [URL_PATTERN.sub(" ", text) if text else "" for text in texts]
    eligible = [i for i, caption in enumerate(captions) if _content_word_count(caption) >= MIN_CONTENT_WORDS]
    if len(eligible) < 2:
        return {}

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vectorizer.fit_transform([captions[i] for i in eligible])
    similarities = (matrix @ matrix.T).tocoo()

    pairs: dict[tuple[int, int], float] = {}
    for row, column, value in zip(similarities.row, similarities.col, similarities.data):
        if row < column and value >= threshold:
            pairs[(eligible[row], eligible[column])] = min(float(value), 1.0)
    return pairs


def normalise_url(url: str) -> str | None:
    """Same page, same string: ignores scheme case, host case, fragment and trailing slash."""
    try:
        parts = urlsplit(url.strip().rstrip(".,;:!?"))
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def urls_in_post(url: str | None, text: str | None) -> set[str]:
    candidates = list(URL_PATTERN.findall(text)) if text else []
    if url:
        candidates.append(url)
    return {normalised for normalised in map(normalise_url, candidates) if normalised}
