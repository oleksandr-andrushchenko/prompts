import sys

import httpx


sys.path[:0] = ["/project/web-lambda", "/project/shared"]
import web_utils


class ThreadsResponse:
    status_code = 200

    def json(self):
        return {
            "data": [
                {
                    "id": "thread-1",
                    "username": "creator",
                    "text": "A useful AI workflow",
                    "timestamp": "2026-09-24T12:00:00+0000",
                    "media_type": "TEXT_POST",
                    "permalink": "https://www.threads.net/@creator/post/example",
                },
                {
                    "id": "unsafe-thread",
                    "text": "Unsafe external link",
                    "permalink": "https://example.com/not-threads",
                },
            ]
        }

    def raise_for_status(self):
        return None


def test_hot_threads_posts_require_server_token(monkeypatch):
    monkeypatch.setitem(web_utils.get_config(), "threads_access_token", None)
    posts, error = web_utils.get_hot_threads_posts(["AI"], "RECENT")
    assert posts == []
    assert error == "Threads search is not configured."


def test_hot_threads_posts_are_normalized_cached_and_limited_to_threads_links(monkeypatch):
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return ThreadsResponse()

    web_utils._threads_cache.clear()
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setitem(web_utils.get_config(), "threads_access_token", "test-token")
    monkeypatch.setitem(web_utils.get_config(), "threads_request_delay_seconds", 0)

    posts, error = web_utils.get_hot_threads_posts(["AI"], "TOP")
    cached_posts, cached_error = web_utils.get_hot_threads_posts(["AI"], "TOP")

    assert error is None
    assert cached_error is None
    assert posts == cached_posts
    assert len(posts) == 1
    assert posts[0]["id"] == "thread-1"
    assert posts[0]["matched_tag"] == "AI"
    assert len(requests) == 1
    assert requests[0][0] == "https://graph.threads.net/keyword_search"
    assert requests[0][1]["params"]["search_mode"] == "KEYWORD"
    assert requests[0][1]["params"]["search_type"] == "TOP"
