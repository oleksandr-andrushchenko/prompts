import os
import sys
from pathlib import Path

project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[1]))
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "api-lambda"))

import api_utils
import shared_utils
from query_dtos import ModelQueryDTO


def test_get_models_queries_registry_partition(monkeypatch):
    calls = []

    def query_dynamodb_table(**kwargs):
        calls.append(kwargs)
        return {"Items": [{
            "pk": "MODEL",
            "sk": "openai-gpt-5-7",
            "name": "openai-gpt-5-7",
        }]}

    monkeypatch.setattr(shared_utils, "query_dynamodb_table", query_dynamodb_table)

    models = shared_utils.get_models(ModelQueryDTO(prefix="GPT-5.7", limit=5))

    assert models == [shared_utils.Model("openai-gpt-5-7", "openai-gpt-5-7")]
    assert calls[0]["limit"] == 5
    assert calls[0].get("index_name") is None


def test_model_registry_updates_are_idempotent_upserts(monkeypatch):
    monkeypatch.setattr(api_utils, "get_dynamodb_table_name", lambda: "test-table")
    transacts = []

    api_utils.add_model_registry_updates_transact(
        transacts, ["acme-dream-2-1", "acme-dream-2-1"], 123
    )

    assert len(transacts) == 1
    update = transacts[0]["Update"]
    assert update["Key"] == {"pk": "MODEL", "sk": "acme-dream-2-1"}
    assert "if_not_exists" in update["UpdateExpression"]
    assert "published_prompts_count" in update["UpdateExpression"]
    assert update["ExpressionAttributeValues"][":zero"] == 0


def test_model_published_count_updates_are_deduplicated(monkeypatch):
    monkeypatch.setattr(api_utils, "get_dynamodb_table_name", lambda: "test-table")
    transacts = []

    api_utils.add_model_published_count_updates_transact(
        transacts, ["acme-dream-2-1", "acme-dream-2-1"], -1, 123
    )

    assert len(transacts) == 1
    update = transacts[0]["Update"]
    assert update["Key"] == {"pk": "MODEL", "sk": "acme-dream-2-1"}
    assert update["ExpressionAttributeValues"][":default_count"] == 1
    assert update["ExpressionAttributeValues"][":delta"] == -1


def test_get_models_combines_static_and_dynamic_catalog(monkeypatch):
    monkeypatch.setattr(shared_utils, "query_dynamodb_table", lambda **_kwargs: {"Items": [{
        "pk": "MODEL",
        "sk": "openai-gpt-5-7",
        "name": "openai-gpt-5-7",
        "published_prompts_count": 3,
    }]})

    models = shared_utils.get_models(ModelQueryDTO(prefix="openai-gpt-5", limit=5))

    assert shared_utils.Model("openai-gpt-5-*", "openai-gpt-5-*") in models
    assert shared_utils.Model("openai-gpt-5-7", "openai-gpt-5-7", 3) in models


def test_get_models_paginates_merged_catalog(monkeypatch):
    calls = []

    def query_dynamodb_table(**kwargs):
        calls.append(kwargs)
        return {"Items": [], "LastEvaluatedKey": {"pk": "MODEL", "sk": "unused"}}

    monkeypatch.setattr(shared_utils, "query_dynamodb_table", query_dynamodb_table)

    first_page = shared_utils.get_models(ModelQueryDTO(limit=2))
    second_page = shared_utils.get_models(ModelQueryDTO(limit=2, offset=first_page[-1].offset))

    assert len(first_page) == len(second_page) == 2
    assert first_page[-1].slug < second_page[0].slug
    assert second_page[-1].offset
    assert calls[1]["exclusive_start_key"] == {"pk": "MODEL", "sk": first_page[-1].slug}


def test_model_fragment_propagates_pagination_offset():
    fragment = project_root / "shared/templates/fragments/model.html"

    assert 'data-offset="{{ model.offset }}"' in fragment.read_text()
