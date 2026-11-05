"""Build an account-similarity graph in which every edge carries its observed evidence.

This is not a directional propagation graph. It does not represent X repost,
quote, or reply relationships. Nodes are accounts, identified by platform and
account ID. Edges link accounts on different posts that share a signal. Rules
are documented in README.md.

The output describes observed similarity. It never scores or labels intent, so
there is deliberately no combined "coordination score" here.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations

import networkx as nx

from .post_ingestion import Post
from .similarity import similar_caption_pairs, urls_in_post

ALGORITHM_NAME = "evidence_signals_v1"

# Above this, the response is too large and the graph too dense for a browser.
MAX_EDGES = 5000

SAME_MEDIA_HASH = "same_media_hash"
SIMILAR_CAPTION = "similar_caption"
SHARED_URL = "shared_url"
CLOSE_POSTING_TIME = "close_posting_time"
SIGNAL_ORDER = (SAME_MEDIA_HASH, SIMILAR_CAPTION, SHARED_URL, CLOSE_POSTING_TIME)
SIGNAL_WORDS = {
    SAME_MEDIA_HASH: "the same media",
    SIMILAR_CAPTION: "similar captions",
    SHARED_URL: "shared URLs",
    CLOSE_POSTING_TIME: "close posting times",
}

LIMITATIONS = [
    "Signals show observed similarity. They don't establish intent or prove malicious coordination.",
    "Legitimate behaviour, such as sharing the same news story, can produce the same signals.",
    "Results depend on the imported records, and posts outside the dataset aren't considered.",
    "Caption similarity is based on shared words, so paraphrased text may not match.",
]


class GraphTooLargeError(ValueError):
    """The dataset has too many relationships to return and draw."""


@dataclass(frozen=True)
class GraphConfig:
    caption_similarity_threshold: float = 0.6
    posting_window_minutes: int = 10
    min_cluster_accounts: int = 3
    min_edge_signals_for_cluster: int = 2


def account_node_id(post: Post) -> str:
    # The same handle on two platforms isn't necessarily the same account.
    return f"{post.platform}:{post.account_id}"


def _format_gap(seconds: float) -> str:
    if seconds < 60:
        return f"{round(seconds)} s"
    return f"{seconds / 60:.1f} min"


def _groups_to_pairs(groups: dict[str, list[int]]) -> dict[tuple[int, int], set[str]]:
    pairs: dict[tuple[int, int], set[str]] = defaultdict(set)
    for key, members in groups.items():
        for pair in combinations(sorted(set(members)), 2):
            pairs[pair].add(key)
    return pairs


class _PostPairEvidence:
    """Every post pair with a content signal. Same-account pairs are excluded."""

    def __init__(self, posts: list[Post], config: GraphConfig):
        self.hashes: dict[tuple[int, int], set[str]] = {}
        self.urls: dict[tuple[int, int], set[str]] = {}
        self.captions: dict[tuple[int, int], float] = {}

        hash_groups: dict[str, list[int]] = defaultdict(list)
        url_groups: dict[str, list[int]] = defaultdict(list)
        for index, post in enumerate(posts):
            if post.media_hash:
                hash_groups[post.media_hash].append(index)
            for url in urls_in_post(post.url, post.text):
                url_groups[url].append(index)

        def different_accounts(pair: tuple[int, int]) -> bool:
            return account_node_id(posts[pair[0]]) != account_node_id(posts[pair[1]])

        similar = similar_caption_pairs([post.text for post in posts], config.caption_similarity_threshold)
        self.hashes = {pair: keys for pair, keys in _groups_to_pairs(hash_groups).items() if different_accounts(pair)}
        self.urls = {pair: keys for pair, keys in _groups_to_pairs(url_groups).items() if different_accounts(pair)}
        self.captions = {pair: score for pair, score in similar.items() if different_accounts(pair)}

    def linked_pairs(self) -> set[tuple[int, int]]:
        return set(self.hashes) | set(self.urls) | set(self.captions)


def _build_signal(signal_type: str, pairs: list[tuple[int, int]], evidence: _PostPairEvidence, posts: list[Post], window_minutes: int) -> dict:
    post_ids = sorted({posts[i].post_id for pair in pairs for i in pair})
    count = len(pairs)
    post_pairs = f"Post pairs: {count}."

    if signal_type == SAME_MEDIA_HASH:
        hashes = sorted({key for pair in pairs for key in evidence.hashes[pair]})
        text = f"Same media hash: {', '.join(hashes)}. {post_pairs}"
    elif signal_type == SHARED_URL:
        urls = sorted({key for pair in pairs for key in evidence.urls[pair]})
        text = f"Same URL: {', '.join(urls)}. {post_pairs}"
    elif signal_type == SIMILAR_CAPTION:
        best = max(evidence.captions[pair] for pair in pairs)
        text = f"Highest TF-IDF cosine similarity: {best:.2f}. {post_pairs}"
    else:
        closest = min(abs((posts[a].timestamp - posts[b].timestamp).total_seconds()) for a, b in pairs)
        text = f"Posts with shared content within {window_minutes} min. Closest gap: {_format_gap(closest)}. {post_pairs}"

    return {"type": signal_type, "evidence": text, "post_ids": post_ids, "post_pair_count": count}


def _build_edges(posts: list[Post], config: GraphConfig) -> list[dict]:
    evidence = _PostPairEvidence(posts, config)
    window_seconds = config.posting_window_minutes * 60

    # Timing is only recorded for posts that already share content. On its own,
    # posting at the same moment would link every busy hour's unrelated posts.
    close_in_time = {
        pair
        for pair in evidence.linked_pairs()
        if abs((posts[pair[0]].timestamp - posts[pair[1]].timestamp).total_seconds()) <= window_seconds
    }

    by_signal = {
        SAME_MEDIA_HASH: evidence.hashes,
        SIMILAR_CAPTION: evidence.captions,
        SHARED_URL: evidence.urls,
        CLOSE_POSTING_TIME: close_in_time,
    }

    grouped: dict[tuple[str, str], dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    for signal_type, pairs in by_signal.items():
        for pair in pairs:
            source, target = sorted((account_node_id(posts[pair[0]]), account_node_id(posts[pair[1]])))
            grouped[(source, target)][signal_type].append(pair)

    if len(grouped) > MAX_EDGES:
        raise GraphTooLargeError(
            f"This dataset produces {len(grouped)} relationships, and the limit is {MAX_EDGES}. "
            "Try importing a smaller set of posts."
        )

    edges = []
    for (source, target), signals in sorted(grouped.items()):
        edges.append(
            {
                "id": f"{source}__{target}",
                "source": source,
                "target": target,
                "signals": [
                    _build_signal(signal_type, sorted(signals[signal_type]), evidence, posts, config.posting_window_minutes)
                    for signal_type in SIGNAL_ORDER
                    if signal_type in signals
                ],
            }
        )
    return edges


def _build_clusters(edges: list[dict], config: GraphConfig) -> list[dict]:
    """A cluster is a connected group of accounts joined by multi-signal edges."""
    graph = nx.Graph()
    for edge in edges:
        if len(edge["signals"]) >= config.min_edge_signals_for_cluster:
            graph.add_edge(edge["source"], edge["target"])

    components = [c for c in nx.connected_components(graph) if len(c) >= config.min_cluster_accounts]
    components.sort(key=lambda component: (-len(component), min(component)))

    clusters = []
    for number, component in enumerate(components, start=1):
        signal_types = {
            signal["type"]
            for edge in edges
            if edge["source"] in component and edge["target"] in component
            for signal in edge["signals"]
        }
        ordered = [signal_type for signal_type in SIGNAL_ORDER if signal_type in signal_types]
        clusters.append(
            {
                "cluster_id": f"cluster_{number}",
                "account_ids": sorted(component),
                "signals": ordered,
                "summary": f"{len(component)} accounts linked by {', '.join(SIGNAL_WORDS[s] for s in ordered)}.",
            }
        )
    return clusters


def build_graph(posts: list[Post], config: GraphConfig | None = None) -> dict:
    config = config or GraphConfig()
    edges = _build_edges(posts, config)
    clusters = _build_clusters(edges, config)
    cluster_by_account = {account: c["cluster_id"] for c in clusters for account in c["account_ids"]}

    accounts: dict[str, dict] = {}
    for post in posts:
        node_id = account_node_id(post)
        node = accounts.setdefault(
            node_id,
            {
                "id": node_id,
                "type": "account",
                "label": post.account_id,
                "account_id": post.account_id,
                "platform": post.platform,
                "cluster_id": cluster_by_account.get(node_id),
                "post_count": 0,
            },
        )
        node["post_count"] += 1

    return {
        "nodes": [accounts[node_id] for node_id in sorted(accounts)],
        "edges": edges,
        "clusters": clusters,
        "algorithm": {"name": ALGORITHM_NAME, "settings": asdict(config)},
        "limitations": LIMITATIONS,
    }
