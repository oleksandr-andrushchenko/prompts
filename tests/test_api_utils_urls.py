import os
import sys
from pathlib import Path
from types import SimpleNamespace


project_root = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "api-lambda"))
sys.path.insert(0, str(project_root / "scripts"))

import app_config
from shared_utils import get_prompt_url
from utils import get_web_request


def test_script_request_builds_human_readable_prompt_url(monkeypatch):
    prompt = SimpleNamespace(
        id="bcd38103-ae4d-4da6-af76-780707d1185c",
        slug="useful-prompt",
        user_id="user-id",
        user_slug="prompt-author",
    )
    monkeypatch.setitem(app_config.config, "web_base_url", "https://example.com/")

    assert get_prompt_url(get_web_request(), prompt, absolute=True) == (
        "https://example.com/@prompt-author/useful-prompt"
    )


def test_script_request_builds_id_url_when_prompt_has_no_user_slug(monkeypatch):
    prompt = SimpleNamespace(
        id="bcd38103-ae4d-4da6-af76-780707d1185c",
        slug="useful-prompt",
        user_id="user-id",
        user_slug=None,
    )
    monkeypatch.setitem(app_config.config, "web_base_url", "https://example.com")

    assert get_prompt_url(get_web_request(), prompt, absolute=True) == (
        "https://example.com/prompts/bcd38103-ae4d-4da6-af76-780707d1185c"
    )
