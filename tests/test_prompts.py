import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[1]))
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "web-lambda"))

previous_cwd = os.getcwd()
os.chdir(project_root / "shared")
import shared_utils
import web_utils
from query_dtos import PromptQueryDTO
os.chdir(previous_cwd)


def prompt(prompt_id, tags, rating, offset=None):
    return SimpleNamespace(
        id=prompt_id,
        tags=tags,
        rating=rating,
        status="published",
        offset=offset,
    )


def test_popular_prompts_by_tags_continues_past_page_without_matches(monkeypatch):
    pages = {
        None: [prompt("global-1", ["databases"], 30, "next-page")],
        "next-page": [prompt("aws-1", ["aws"], 20)],
    }
    offsets = []

    def get_popular_prompts(query, cur_user):
        offsets.append(query.offset)
        return pages[query.offset]

    monkeypatch.setattr(shared_utils, "get_popular_prompts", get_popular_prompts)

    result = shared_utils.get_popular_prompts_by_tags(PromptQueryDTO(tags=["aws"], limit=10))

    assert [item.id for item in result] == ["aws-1"]
    assert offsets == [None, "next-page"]


def test_popular_prompts_by_tags_uses_last_match_as_pagination_cursor(monkeypatch):
    page = [
        prompt("global-1", ["databases"], 30),
        prompt("aws-1", ["aws"], 20),
        prompt("aws-2", ["aws"], 10),
        prompt("aws-3", ["aws"], 5, "end-of-query-page"),
    ]
    monkeypatch.setattr(shared_utils, "get_popular_prompts", lambda query, cur_user: page)

    result = shared_utils.get_popular_prompts_by_tags(PromptQueryDTO(tags=["aws"], limit=2))

    assert [item.id for item in result] == ["aws-1", "aws-2"]
    assert shared_utils.decode_offset(result[-1].offset) == {
        "pk": "PROMPT#aws-2",
        "sk": "META",
        "prompt_status_pk": "PROMPT#published",
        "rating_sk": 10,
    }


def test_related_prompts_query_each_tag_and_batch_load_candidates(monkeypatch):
    current = prompt("current", ["aws", "python"], 40)
    candidates = [
        prompt("related-1", ["aws"], 30),
        prompt("related-2", ["aws", "python"], 20),
    ]
    captured_queries = []
    captured_batch_ids = []

    def get_prompt_ids_by_tag(tag, limit):
        captured_queries.append((tag, limit))
        return {
            "aws": ["current", "related-1", "related-2"],
            "python": ["current", "related-2"],
        }[tag]

    def get_prompts_by_ids(prompt_ids):
        captured_batch_ids.extend(prompt_ids)
        return candidates

    monkeypatch.setattr(web_utils, "_get_prompt_ids_by_tag", get_prompt_ids_by_tag)
    monkeypatch.setattr(web_utils, "_get_prompts_by_ids", get_prompts_by_ids)

    result = asyncio.run(web_utils.get_prompt_related_prompts(current, limit=2))

    assert [item.id for item in result] == ["related-2", "related-1"]
    assert sorted(captured_queries) == [("aws", 3), ("python", 3)]
    assert captured_batch_ids == ["related-1", "related-2"]


def test_related_prompt_batch_read_retries_unprocessed_keys(monkeypatch):
    unprocessed_key = {"pk": "PROMPT#related-2", "sk": "META"}

    class Client:
        def __init__(self):
            self.requests = []

        def batch_get_item(self, RequestItems):
            self.requests.append(RequestItems)
            if len(self.requests) == 1:
                return {
                    "Responses": {"prompts": [{"id": "related-1"}]},
                    "UnprocessedKeys": {"prompts": {"Keys": [unprocessed_key]}},
                }
            return {
                "Responses": {"prompts": [{"id": "related-2"}]},
                "UnprocessedKeys": {},
            }

    client = Client()
    table = SimpleNamespace(name="prompts", meta=SimpleNamespace(client=client))
    monkeypatch.setattr(web_utils, "get_dynamodb_table", lambda: table)
    monkeypatch.setattr(web_utils, "prompt_from_dynamodb", lambda item: item["id"])

    result = web_utils._get_prompts_by_ids(["related-1", "related-2"])

    assert result == ["related-1", "related-2"]
    assert client.requests[1] == {"prompts": {"Keys": [unprocessed_key]}}
