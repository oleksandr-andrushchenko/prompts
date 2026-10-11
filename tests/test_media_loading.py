"""Rendering checks for image priority, deferred media, and conditional assets."""
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import FileSystemLoader

project_root = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(project_root / "shared"))

from api_route_metadata import API_URL_ROUTES
from query_dtos import ModelQueryDTO, PromptCommentQueryDTO
from shared_utils import get_jinja2_env, prompt_from_dynamodb, user_from_dynamodb
from web import Application, Request
from web_route_metadata import WEB_URL_ROUTES


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.setdefault(tag, []).append(dict(attrs))


@pytest.fixture
def render():
    app = Application()
    for name, path in (WEB_URL_ROUTES | API_URL_ROUTES).items():
        app.add_url_route(path, name)
    request = Request({
        "type": "http", "method": "GET", "path": "/", "root_path": "", "query_string": b"",
        "scheme": "https", "server": ("example.com", 443), "headers": [], "app": app,
    })
    env = get_jinja2_env()
    env.loader = FileSystemLoader([str(project_root / "web-lambda/templates"), str(project_root / "shared/templates")])
    author = user_from_dynamodb({"id": "creator", "name": "Creator", "username": "creator", "created_at": 1})
    prompt = prompt_from_dynamodb({
        "id": "example", "user_id": author.id, "user_name": author.name, "user_slug": author.username,
        "title": "Example prompt", "prompt_slug": "example", "description": "Example description",
        "template": {"content": "Write a reply.", "format": "text"},
        "status": "published", "rating_sk": 1, "created_at": 1,
        "result_files": [
            {"filename": "first_1200x800.png", "format": "image"},
            {"filename": "second_1200x600.png", "format": "image"},
            {"filename": "result.mp4", "format": "video", "preview_filename": "poster_1920x1080.png"},
            {"filename": "result.mp3", "format": "audio"},
        ],
    })

    def render_template(template, **overrides):
        data = {
            "request": request, "cur_user": None, "prompt": prompt, "prompts": [prompt, prompt],
            "author": author, "category": SimpleNamespace(name="Other", slug="other"),
            "comments": [], "comments_query": PromptCommentQueryDTO(), "related_prompts": [],
        }
        return env.get_template(template).render(**(data | overrides))

    return render_template


def test_first_carousel_image_is_prioritized_and_hidden_images_are_lazy(render):
    elements = Elements(render("prompt.html"))
    images = elements.tags["img"]
    first, second = images[:2]
    assert first["loading"] == "eager"
    assert first["fetchpriority"] == "high"
    assert second["loading"] == "lazy"
    assert "fetchpriority" not in second
    assert first["decoding"] == second["decoding"] == "async"
    assert (first["width"], first["height"]) == ("1200", "800")


def test_media_waits_for_playback_and_video_reserves_its_preview_ratio(render):
    elements = Elements(render("prompt.html"))
    video = elements.tags["video"][0]
    assert video["preload"] == elements.tags["audio"][0]["preload"] == "none"
    assert (video["width"], video["height"]) == ("1920", "1080")
    assert "h-auto" in video["class"].split()


def test_initial_listing_can_prioritize_one_image_while_fragments_stay_lazy(render):
    initial = Elements(render("fragments/prompts.html", eager_prompt_images=1)).tags["img"]
    fragment = Elements(render("fragments/prompts.html")).tags["img"]
    assert [image["loading"] for image in initial] == ["eager", "lazy"]
    assert all(image["loading"] == "lazy" for image in fragment)


def test_tagify_styles_are_in_the_head_and_assets_remain_conditional(render):
    prompt_html = render("prompt.html")
    # The page owns its assets, so use the layout directly to exercise its flags.
    tagify_html = render("layout.html", layout_assets={"tagify": True})
    assert "tagify.css" in tagify_html.split("</head>", 1)[0]
    assert "tagify.polyfills" not in tagify_html
    assert "tagify.css" not in prompt_html
    directory_html = render("models.html", models=[], models_query=ModelQueryDTO())
    assert "tagify" not in directory_html
    assert "masonry.pkgd" not in directory_html
    assert "prism-core" not in directory_html
