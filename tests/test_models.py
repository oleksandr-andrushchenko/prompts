import os
import sys
from pathlib import Path

project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parents[1]))
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "api-lambda"))

import api_utils
from query_dtos import ModelQueryDTO


def test_get_models_queries_registry_partition(monkeypatch):
    calls = []

    def query_dynamodb_table(**kwargs):
        calls.append(kwargs)
        return {"Items": [{
            "pk": "MODEL",
            "sk": "openai-gpt-5-7",
            "name": "openai-gpt-5-7",
            "published_prompts_count": 2,
        }]}

    monkeypatch.setattr(api_utils, "query_dynamodb_table", query_dynamodb_table)

    models = api_utils.get_models(ModelQueryDTO(prefix="GPT-5.7", limit=5))

    assert models == [api_utils.Model("openai-gpt-5-7", "openai-gpt-5-7", 2)]
    assert calls[0]["limit"] == 5
    assert calls[0].get("index_name") is None


def test_model_registry_updates_are_idempotent_upserts(monkeypatch):
    monkeypatch.setattr(api_utils, "get_dynamodb_table_name", lambda: "test-table")
    transacts = []

    api_utils.add_model_registry_updates_transact(
        transacts, ["acme-dream-2-1", "acme-dream-2-1"], 123, 1
    )

    assert len(transacts) == 1
    update = transacts[0]["Update"]
    assert update["Key"] == {"pk": "MODEL", "sk": "acme-dream-2-1"}
    assert "if_not_exists" in update["UpdateExpression"]
    assert update["ExpressionAttributeValues"][":delta"] == 1
