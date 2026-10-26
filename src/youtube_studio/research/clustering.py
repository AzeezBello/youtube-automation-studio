"""Local topic clustering and keyword extraction (TF-IDF cosine + optional neural embeddings)."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from youtube_studio.research.providers.base import ResearchResult

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "result",
        "stub",
        "synthetic",
        "that",
        "the",
        "this",
        "to",
        "video",
        "with",
        "vol",
        "part",
        "full",
        "official",
    }
)


@dataclass
class TopicCluster:
    cluster_id: int
    label: str
    keywords: list[str]
    results: list[ResearchResult] = field(default_factory=list)


EmbedCallable = Callable[[list[str]], list[list[float]]]


class TopicClusterer:
    """Clusters research results into thematic groups and extracts high-signal keywords."""

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.18,
        embed_fn: Optional[EmbedCallable] = None,
    ) -> None:
        self._threshold = similarity_threshold
        self._embed_fn = embed_fn

    def cluster(
        self,
        results: list[ResearchResult],
        *,
        max_clusters: int = 8,
    ) -> list[TopicCluster]:
        if not results:
            return []

        texts = [self._extract_text(r) for r in results]
        token_lists = [self._tokenize(t) for t in texts]

        if self._embed_fn is not None:
            vectors = self._embed_fn(texts)
            sim_matrix = self._dense_cosine_matrix(vectors)
        else:
            tfidf_vecs = self._compute_tfidf(token_lists)
            sim_matrix = self._sparse_cosine_matrix(tfidf_vecs)

        # Greedy leader/centroid clustering
        assigned = [-1] * len(results)
        clusters_idx: list[list[int]] = []

        for i in range(len(results)):
            if assigned[i] != -1:
                continue
            best_c = -1
            best_sim = -1.0
            for c_idx, members in enumerate(clusters_idx):
                avg_sim = sum(sim_matrix[i][m] for m in members) / len(members)
                if avg_sim >= self._threshold and avg_sim > best_sim:
                    best_sim = avg_sim
                    best_c = c_idx

            if best_c != -1:
                clusters_idx[best_c].append(i)
                assigned[i] = best_c
            elif len(clusters_idx) < max_clusters:
                new_c = len(clusters_idx)
                clusters_idx.append([i])
                assigned[i] = new_c
            else:
                # Assign to closest existing cluster
                closest_c = max(
                    range(len(clusters_idx)),
                    key=lambda c_idx: sum(sim_matrix[i][m] for m in clusters_idx[c_idx])
                    / len(clusters_idx[c_idx]),
                )
                clusters_idx[closest_c].append(i)
                assigned[i] = closest_c

        topic_clusters: list[TopicCluster] = []
        for c_id, member_indices in enumerate(clusters_idx):
            member_tokens: list[str] = []
            member_results: list[ResearchResult] = []
            for idx in member_indices:
                member_tokens.extend(token_lists[idx])
                member_results.append(results[idx])
            keywords = self._top_keywords(member_tokens, top_k=5)
            label = " / ".join(keywords[:3]).title() if keywords else f"Topic {c_id + 1}"
            topic_clusters.append(
                TopicCluster(
                    cluster_id=c_id,
                    label=label,
                    keywords=keywords,
                    results=member_results,
                )
            )
        return topic_clusters

    def extract_keywords(self, results: list[ResearchResult], *, top_k: int = 10) -> list[str]:
        all_tokens: list[str] = []
        for r in results:
            all_tokens.extend(self._tokenize(self._extract_text(r)))
        return self._top_keywords(all_tokens, top_k=top_k)

    @staticmethod
    def _extract_text(result: ResearchResult) -> str:
        title = str(result.payload.get("title", ""))
        desc = str(result.payload.get("description", ""))
        tags = " ".join(str(t) for t in result.payload.get("tags", []))
        return f"{title} {title} {desc} {tags}".strip()

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]{3,}", text.lower())
        return [w for w in words if w not in STOPWORDS and not w.isdigit()]

    @staticmethod
    def _top_keywords(tokens: list[str], *, top_k: int = 5) -> list[str]:
        counts = Counter(tokens)
        return [word for word, _ in counts.most_common(top_k)]

    @staticmethod
    def _compute_tfidf(token_lists: list[list[str]]) -> list[dict[str, float]]:
        n_docs = max(1, len(token_lists))
        df: Counter[str] = Counter()
        for tokens in token_lists:
            for term in set(tokens):
                df[term] += 1

        vectors: list[dict[str, float]] = []
        for tokens in token_lists:
            tf = Counter(tokens)
            total = max(1, len(tokens))
            vec: dict[str, float] = {}
            for term, count in tf.items():
                idf = math.log(1.0 + (n_docs / (1.0 + df[term])))
                vec[term] = (count / total) * idf
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            vectors.append({k: v / norm for k, v in vec.items()})
        return vectors

    @staticmethod
    def _sparse_cosine_matrix(vectors: list[dict[str, float]]) -> list[list[float]]:
        n = len(vectors)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            matrix[i][i] = 1.0
            vi = vectors[i]
            for j in range(i + 1, n):
                vj = vectors[j]
                sim = sum(val * vj.get(term, 0.0) for term, val in vi.items())
                matrix[i][j] = sim
                matrix[j][i] = sim
        return matrix

    @staticmethod
    def _dense_cosine_matrix(vectors: list[list[float]]) -> list[list[float]]:
        n = len(vectors)
        matrix = [[0.0] * n for _ in range(n)]
        norms = [math.sqrt(sum(x * x for x in v)) or 1.0 for v in vectors]
        for i in range(n):
            matrix[i][i] = 1.0
            for j in range(i + 1, n):
                dot = sum(a * b for a, b in zip(vectors[i], vectors[j]))
                sim = dot / (norms[i] * norms[j])
                matrix[i][j] = sim
                matrix[j][i] = sim
        return matrix
