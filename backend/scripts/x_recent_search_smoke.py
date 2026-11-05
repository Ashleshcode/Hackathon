"""Manual X recent-search smoke test.

This script calls the official API and is not part of pytest.
It requires X_BEARER_TOKEN in the environment or a local .env file.
It prints post ids and relationship types only. It does not print the token,
media URLs, or variant URLs.

Example:
    .venv\\Scripts\\python.exe backend/scripts/x_recent_search_smoke.py "lang:en hello"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.x.client import XConnectorError, build_client
from app.x.parse import parse_search_payload


def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or "lang:en hello"
    try:
        client = build_client()
    except XConnectorError as error:
        print(error.message)
        return 2
    try:
        payload = client.search_page(query, page_size=10)
    except XConnectorError as error:
        print(f"{error.code}: {error.message}")
        return 1
    finally:
        client.close()
    parsed = parse_search_payload(payload)
    print(f"query={query}")
    print("search_window=preceding_seven_days")
    print(f"posts={len(parsed['posts'])}")
    print(f"next_token={'present' if parsed['next_token'] else 'absent'}")
    for post in parsed["posts"]:
        relationships = ",".join(item["type"] for item in post["references"]) or "none"
        print(f"post_id={post['post_id']} author_id={post['author_id'] or 'absent'} relationships={relationships} media_keys={len(post['media_keys'])}")
    print(f"accounts={len(parsed['accounts'])}")
    print(f"media={len(parsed['media'])}")
    print("analysis=not_performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
