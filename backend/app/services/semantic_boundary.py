import re
from collections import Counter
from collections.abc import Callable
from math import sqrt

TOKEN_PATTERN = re.compile(r"[\w\u3400-\u4dbf\u4e00-\u9fff]+", re.UNICODE)
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "is",
    "are",
    "this",
    "that",
    "we",
    "本文",
    "一种",
    "以及",
    "进行",
}


class SemanticBoundaryService:
    """Cheap local boundary scorer with an optional embedding similarity hook."""

    def __init__(
        self,
        embedding_similarity: Callable[[str, str], float] | None = None,
    ) -> None:
        self.embedding_similarity = embedding_similarity

    def score(self, left: str, right: str) -> tuple[float, dict[str, float | bool]]:
        lexical = self.lexical_similarity(left, right)
        embedding = (
            self.embedding_similarity(left, right)
            if self.embedding_similarity is not None
            else None
        )
        continuity = lexical if embedding is None else lexical * 0.45 + embedding * 0.55
        discourse = self._has_discourse_shift(right)
        boundary = min(1.0, max(0.0, 1 - continuity + (0.12 if discourse else 0)))
        return boundary, {
            "lexicalSimilarity": round(lexical, 4),
            "embeddingSimilarity": (
                round(embedding, 4) if embedding is not None else -1.0
            ),
            "discourseMarker": discourse,
        }

    def topic(self, text: str, limit: int = 5) -> str | None:
        tokens = [token for token in self._tokens(text) if token not in STOPWORDS]
        if not tokens:
            return None
        return ", ".join(token for token, _ in Counter(tokens).most_common(limit))

    def lexical_similarity(self, left: str, right: str) -> float:
        left_counts = Counter(self._tokens(left))
        right_counts = Counter(self._tokens(right))
        if not left_counts or not right_counts:
            return 0.0
        shared = left_counts.keys() & right_counts.keys()
        numerator = sum(left_counts[token] * right_counts[token] for token in shared)
        left_norm = sqrt(sum(value * value for value in left_counts.values()))
        right_norm = sqrt(sum(value * value for value in right_counts.values()))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [
            token.casefold()
            for token in TOKEN_PATTERN.findall(text)
            if len(token.strip()) > 1
        ]

    @staticmethod
    def _has_discourse_shift(text: str) -> bool:
        normalized = text.strip().casefold()
        markers = (
            "however",
            "in contrast",
            "on the other hand",
            "nevertheless",
            "therefore",
            "in conclusion",
            "然而",
            "相比之下",
            "另一方面",
            "综上",
            "因此",
        )
        return any(normalized.startswith(marker) for marker in markers)
