#!/usr/bin/env python3

import json
import os
import time
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import quote

import pytest
from pyquery import PyQuery as pq

from test_utils import (
    recreate_dynamodb_table,
    get_guest_client,
    get_logged_in_client,
    get,
    prompt,
    patch,
    delete,
    regular_user,
    regular_2_user,
    root_user,
    set_dynamodb_user_permissions,
    get_dynamodb_user,
    get_dynamodb_user_by_email,
    get_dynamodb_prompt,
    dynamodb_table,
)

pytestmark = pytest.mark.functional


def get_client(request, user):
    client_name = f"{user}_user_client"
    client = request.getfixturevalue(client_name)
    return client


def get_user(client, user_alias) -> pq:
    user = get_dynamodb_user(user_ids[user_alias])
    resp = get(client, f"/users/{user['id']}")
    assert resp.status_code == 200
    doc = pq(resp.text)
    assert user["name"] in doc("head title").text()
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "Person"
    assert schema["url"].startswith("http")
    assert schema["breadcrumb"]["itemListElement"][-1]["name"] == user["name"]
    assert all(value is not None for value in schema.values())
    assert doc('meta[property="og:type"]').attr("content") == "profile"
    assert doc('meta[name="description"]').attr("content").startswith(user["name"])
    main_el = doc("main")
    assert user["name"] in main_el("h1").text()
    return doc


def get_logged_in_user_id(user_data: dict) -> str:
    return get_dynamodb_user_by_email(user_data["email"])["id"]


def get_index(client):
    resp = get(client, "/")
    assert resp.status_code == 200
    doc = pq(resp.text)
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "WebSite"
    assert schema["url"].startswith("http")
    assert doc('meta[name="robots"]').attr("content") == "index, follow"
    assert doc('link[rel="canonical"]').attr("href").startswith("http")
    return doc


def get_users(client):
    resp = get(client, "/users")
    assert resp.status_code == 200
    doc = pq(resp.text)
    assert "users" in doc("head title").text().lower()
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "CollectionPage"
    assert schema["mainEntity"]["@type"] == "ItemList"
    assert schema["breadcrumb"]["itemListElement"][-1]["name"] == "Users"
    assert doc('link[rel="canonical"]').attr("href").endswith("/users")
    main_el = doc("main")
    assert "users" in main_el("h1").text().lower()
    return doc


def get_user_by_id(client, user):
    resp = get(client, f"/users/{user['id']}")
    assert resp.status_code == 200
    return pq(resp.text)


def get_user_by_slug(client, user):
    resp = get(client, f"/{user['username']}")
    assert resp.status_code == 200
    return pq(resp.text)


def get_prompts(client):
    resp = get(client, "/prompts")
    assert resp.status_code == 200
    doc = pq(resp.text)
    assert "prompts" in doc("head title").text().lower()
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "CollectionPage"
    assert schema["mainEntity"]["@type"] == "ItemList"
    assert schema["breadcrumb"]["itemListElement"][-1]["name"] == "Prompts"
    assert doc('link[rel="canonical"]').attr("href").endswith("/prompts")
    main_el = doc("main")
    assert "prompts" in main_el("h1").text().lower()
    return doc


def get_prompt_by_id(client, prompt):
    resp = get(client, f"/prompts/{prompt['id']}")
    assert resp.status_code == 200
    return pq(resp.text)


def get_prompt_by_slug(client, prompt):
    resp = get(client, f"/{prompt['user_slug']}/{prompt['slug']}")
    assert resp.status_code == 200
    return pq(resp.text)


def get_contacts(client):
    resp = get(client, "/contacts")
    assert resp.status_code == 200
    doc = pq(resp.text)
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "ContactPage"
    assert schema["breadcrumb"]["itemListElement"][-1]["name"] == "Contacts"
    assert doc('meta[name="description"]').attr("content").startswith("Contact PromptCatalog")
    return doc


def get_user_href(user: dict) -> str:
    if username := user.get("username"):
        return f"/{username}"
    return f"/users/{user['id']}"


def get_prompt_href(prompt: dict, user: dict | None = None) -> str:
    if username := user.get("username"):
        return f"/{username}"
    return f"/users/{user['id']}"


def check_header(doc, user_alias: str | None):
    header_el = doc("header")
    assert header_el('a[href$="/"]')
    assert header_el('a[href$="/prompts"]')
    assert header_el('a[href$="/users"]')
    assert header_el('a[href$="/contacts"]')
    if user_alias:
        assert header_el('a[href$="/prompts/new"]')
        assert header_el('a[href$="/logout"]')
        user = get_dynamodb_user(user_ids[user_alias])
        assert header_el('a[href$="' + get_user_href(user) + '"]')
    else:
        assert header_el('a[href$="/login"]')
        # todo: "*=" - contains
        user_view_el = header_el('a[href="/users/*"]')
        assert not user_view_el


def check_user_impressions(doc, followers_count: int, following_count: int, follow_control: bool, block_control: bool):
    main_el = doc("main")
    user_impressions_el = main_el(".user-impressions")
    assert user_impressions_el
    assert int(user_impressions_el(".followers-count").text()) == followers_count
    assert int(user_impressions_el(".following-count").text()) == following_count
    has_user_follow = user_impressions_el(".btn-user-follow")
    if follow_control:
        assert has_user_follow
    else:
        assert not has_user_follow
    has_user_block = user_impressions_el(".btn-user-block")
    if block_control:
        assert has_user_block
    else:
        assert not has_user_block


def check_user_edit(doc, user_alias: str | None):
    main_el = doc("main")
    if user_alias:
        user = get_dynamodb_user(user_ids[user_alias])
        user_edit_el = main_el('a[href$="/users/' + user['id'] + '/edit"]')
        assert user_edit_el
    else:
        # todo:
        user_edit_el = main_el('a[href="/users/*/edit"]')
        assert not user_edit_el


def check_user_status(doc, activate_control: bool, ban_control: bool):
    main_el = doc("main")
    activate_el = main_el(".btn-user-activate")
    if activate_control:
        assert activate_el
    else:
        assert not activate_el
    ban_el = main_el(".btn-user-ban")
    if ban_control:
        assert ban_el
    else:
        assert not ban_el


def check_user(doc, followers_count: int, following_count: int, follow_control: bool, block_control: bool,
               user_alias: str | None, activate_control: bool, ban_control: bool):
    check_user_impressions(doc, followers_count=followers_count, following_count=following_count,
                           follow_control=follow_control, block_control=block_control)
    check_user_edit(doc, user_alias=user_alias)
    check_user_status(doc, activate_control=activate_control, ban_control=ban_control)


def check_prompts(doc, prompts_count: int, unpublished_control: bool, rejected_control: bool, tags_control: bool,
                   popular_control: bool, prompt_aliases: list[str], css_id="prompts"):
    main_el = doc("main")
    prompts_el = main_el("#" + css_id)
    if prompts_count:
        assert len(prompts_el(".prompt")) == prompts_count
        for prompt_alias in prompt_aliases:
            prompt = get_dynamodb_prompt(prompt_ids[prompt_alias])
            user = get_dynamodb_user(prompt["user_id"])
            prompt_el = main_el('a[href$="' + get_prompt_href(prompt, user) + '"]')
            assert prompt_el
            assert prompt["title"] in prompt_el.text()
    else:
        assert not prompts_el
    form_el = main_el("form")
    status_controls_el = form_el if form_el else main_el
    unpublished_el = status_controls_el('a[href*="status=unpublished"]')
    if unpublished_control:
        assert unpublished_el
    else:
        assert not unpublished_el
    rejected_el = status_controls_el('a[href*="status=rejected"]')
    if rejected_control:
        assert rejected_el
    else:
        assert not rejected_el
    tags_el = form_el('#tags-input')
    if tags_control:
        assert tags_el
    else:
        assert not tags_el
    popular_el = form_el('a[href*="popular"].bi-star')
    if popular_control:
        assert popular_el
    else:
        assert not popular_el


def check_users(doc, users_count: int, banned_control: bool, popular_control: bool, user_aliases: list[str],
                css_id="users"):
    main_el = doc("main")
    users_el = main_el("#" + css_id)
    if users_count:
        assert len(users_el(".user")) == users_count
        for user_alias in user_aliases:
            user = get_dynamodb_user(user_ids[user_alias])
            user_el = main_el('a[href$="' + get_user_href(user) + '"]')
            assert user_el
            assert user["name"] in user_el.text()
    else:
        assert not users_el
    form_el = main_el("form")
    banned_el = form_el('a[href*="status=banned"]')
    if banned_control:
        assert banned_el
    else:
        assert not banned_el
    popular_el = form_el('a[href*="popular"].bi-heart')
    if popular_control:
        assert popular_el
    else:
        assert not popular_el


def check_latest_prompt_comments(doc, comments_count: int, comment_texts: list[str]):
    main_el = doc("main")
    comments_el = main_el("#latest-prompt-comments")
    if comments_count:
        assert len(comments_el(".prompt-comment")) == comments_count
        rendered_text = comments_el.text()
        for comment_text in comment_texts:
            assert comment_text in rendered_text
    else:
        assert not comments_el


def check_index(doc):
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=False,
                   popular_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=False,
                   popular_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="popular-prompts")
    check_latest_prompt_comments(doc, comments_count=0, comment_texts=[])
    check_users(doc, users_count=0, banned_control=False, popular_control=False, user_aliases=[], css_id="users")
    check_users(doc, users_count=3, banned_control=False, popular_control=False, user_aliases=list(user_ids.keys()),
                css_id="popular-users")


@pytest.fixture(scope="session", autouse=True)
def setup_dynamodb():
    recreate_dynamodb_table()


@pytest.fixture(scope="session")
def guest_client():
    return get_guest_client()


@pytest.fixture(scope="session")
def regular_user_client():
    return get_logged_in_client(regular_user)


@pytest.fixture(scope="session")
def regular_2_user_client():
    return get_logged_in_client(regular_2_user)


@pytest.fixture(scope="session")
def root_user_client():
    return get_logged_in_client(root_user)


user_ids = {}
prompt_ids = {}


def test_root_user_first_login(root_user_client):
    user_ids["root"] = get_logged_in_user_id(root_user)
    set_dynamodb_user_permissions(user_ids["root"], ["root"])


@pytest.mark.parametrize("user_alias", ["regular", "regular_2"])
def test_regular_user_first_login(request, user_alias):
    get_client(request, user_alias)
    user_data = regular_user if user_alias == "regular" else regular_2_user
    user_ids[user_alias] = get_logged_in_user_id(user_data)


def test_guest_user_get_index(guest_client):
    doc = get_index(guest_client)
    check_header(doc, user_alias=None)
    check_index(doc)


@pytest.mark.parametrize("user_alias", ["regular", "root"])
def test_non_guest_user_get_index(request, user_alias):
    client = get_client(request, user_alias)
    doc = get_index(client)
    check_header(doc, user_alias=user_alias)
    check_index(doc)


@pytest.mark.parametrize("user_alias", ["regular", "root"])
def test_guest_user_get_user(guest_client, user_alias):
    doc = get_user(guest_client, user_alias)
    check_header(doc, user_alias=None)
    check_user(doc, followers_count=0, following_count=0, follow_control=False, block_control=False, user_alias=None,
               activate_control=False, ban_control=False)
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=False,
                   popular_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


@pytest.mark.parametrize("user_alias", ["regular_2", "root"])
def test_regular_user_get_other_user(regular_user_client, user_alias):
    doc = get_user(regular_user_client, user_alias)
    check_header(doc, user_alias="regular")
    check_user(doc, followers_count=0, following_count=0, follow_control=True, block_control=True, user_alias=None,
               activate_control=False, ban_control=False)
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=False,
                   popular_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


def test_regular_user_get_self_user(regular_user_client):
    user_alias = "regular"
    doc = get_user(regular_user_client, user_alias)
    check_header(doc, user_alias=user_alias)
    check_user(doc, followers_count=0, following_count=0, follow_control=False, block_control=False,
               user_alias=user_alias, activate_control=False, ban_control=False)
    check_prompts(doc, prompts_count=0, unpublished_control=True, rejected_control=True, popular_control=False,
                   tags_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


def test_root_user_get_user(root_user_client):
    user_alias = "regular"
    doc = get_user(root_user_client, user_alias)
    check_header(doc, user_alias="root")
    check_user(doc, followers_count=0, following_count=0, follow_control=True, block_control=True,
               user_alias=user_alias, activate_control=False, ban_control=True)
    check_prompts(doc, prompts_count=0, unpublished_control=True, rejected_control=True, popular_control=False,
                   tags_control=False, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


def test_guest_user_get_users(guest_client):
    doc = get_users(guest_client)
    check_users(doc, users_count=3, banned_control=False, popular_control=True, user_aliases=list(user_ids.keys()),
                css_id="users")


def test_regular_user_get_users(regular_user_client):
    doc = get_users(regular_user_client)
    check_users(doc, users_count=3, banned_control=False, popular_control=True, user_aliases=list(user_ids.keys()),
                css_id="users")


def test_root_user_get_users(root_user_client):
    doc = get_users(root_user_client)
    check_users(doc, users_count=3, banned_control=True, popular_control=True, user_aliases=list(user_ids.keys()),
                css_id="users")


def test_guest_user_get_prompts(guest_client):
    doc = get_prompts(guest_client)
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=True,
                   popular_control=True, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


def test_regular_user_get_prompts(regular_user_client):
    doc = get_prompts(regular_user_client)
    check_prompts(doc, prompts_count=0, unpublished_control=False, rejected_control=False, tags_control=True,
                   popular_control=True, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


def test_root_user_get_prompts(root_user_client):
    doc = get_prompts(root_user_client)
    check_prompts(doc, prompts_count=0, unpublished_control=True, rejected_control=True, tags_control=True,
                   popular_control=True, prompt_aliases=list(prompt_ids.keys()), css_id="prompts")


@pytest.mark.parametrize("user_alias", ["regular", "root"])
def test_get_contacts(request, user_alias):
    client = get_client(request, user_alias)
    doc = get_contacts(client)
    check_header(doc, user_alias=user_alias)


@pytest.mark.parametrize("path", ["/any", "/any/any", "/missing", "/foo/bar"])
def test_not_found(guest_client, path):
    resp = get(guest_client, path)
    assert resp.status_code == 404


@pytest.mark.parametrize("user_alias", ["regular", "root"])
def test_logout(request, user_alias):
    client = get_client(request, user_alias)
    resp = get(client, "/logout", allow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/logout-callback")


def test_regular_user_can_create_prompt_comment():
    comment_user_client = get_logged_in_client({
        "sub": "commenter-sub",
        "iss": "commenter-iss",
        "email": "commenter@example.com",
    })
    prompt_id = str(uuid.uuid4())
    owner_id = user_ids["root"]
    now = int(time.time() * 1000)

    dynamodb_table.put_item(Item={
        "pk": f"PROMPT#{prompt_id}",
        "sk": "META",
        "id": prompt_id,
        "title": "Regular comment permission test prompt",
        "prompt_slug": "regular-comment-permission-test-prompt",
        "user_id": owner_id,
        "content": "Long form prompt content for integration testing. " * 120,
        "tags": ["testing"],
        "rating_sk": now,
        "status": "published",
        "created_at": now,
        "published_at": now,
        "prompt_status_pk": "PROMPT#published",
        "prompt_user_status_pk": f"PROMPT#{owner_id}#published",
        "comments_count": 0,
    })

    resp = prompt(comment_user_client, f"/prompts/{prompt_id}/comment", json={
        "text": "Regular users should be allowed to comment."
    })

    assert resp.status_code == 200
    assert resp.json().endswith(f"/prompts/{prompt_id}")


def test_index_shows_latest_prompt_comments(guest_client):
    prompt_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    prompt_title = "Latest comments test prompt"
    prompt_ids["latest_comments"] = prompt_id

    dynamodb_table.put_item(Item={
        "pk": f"PROMPT#{prompt_id}",
        "sk": "META",
        "id": prompt_id,
        "title": prompt_title,
        "prompt_slug": "latest-comments-test-prompt",
        "user_id": user_id,
        "content": "Long form prompt content for integration testing. " * 120,
        "tags": ["testing"],
        "rating_sk": now,
        "status": "published",
        "created_at": now,
        "published_at": now,
        "prompt_status_pk": "PROMPT#published",
        "prompt_user_status_pk": f"PROMPT#{user_id}#published",
        "comments_count": 6,
    })

    comment_texts = []
    for i in range(6):
        comment_id = f"{now + i}#{uuid.uuid4()}"
        comment_text = f"Latest comment integration text {i}"
        dynamodb_table.put_item(Item={
            "pk": f"PROMPT#{prompt_id}",
            "sk": f"COMMENT#{comment_id}",
            "id": comment_id,
            "prompt_id": prompt_id,
            "prompt_comment_pk": "PROMPT_COMMENT",
            "prompt_title": prompt_title,
            "comment_prompt_slug": "latest-comments-test-prompt",
            "user_id": user_id,
            "user_name": "Comment Author",
            "text": comment_text,
            "created_at": now + i,
        })
        comment_texts.append(comment_text)

    doc = get_index(guest_client)
    check_latest_prompt_comments(doc, comments_count=3, comment_texts=list(reversed(comment_texts[-3:]))) 

    comments = [pq(el).text() for el in doc("#latest-prompt-comments .prompt-comment").items()]
    assert comment_texts[5] in comments[0]
    assert comment_texts[3] in comments[-1]
    assert comment_texts[0] not in doc("#latest-prompt-comments").text()
    assert prompt_title in doc("#latest-prompt-comments").text()


@pytest.mark.parametrize(("legacy_path", "prompt_path"), [
    ("/posts", "/prompts"),
    ("/post", "/prompts"),
    ("/posts/new", "/prompts/new"),
    ("/post/new", "/prompts/new"),
    ("/posts/example-id", "/prompts/example-id"),
    ("/post/example-id", "/prompts/example-id"),
    ("/posts/example-id/edit", "/prompts/example-id/edit"),
    ("/post/example-id/edit", "/prompts/example-id/edit"),
    ("/latest/python/posts", "/latest/python/prompts"),
])
def test_legacy_prompt_page_urls_redirect_to_prompts(guest_client, legacy_path, prompt_path):
    response = get(guest_client, f"{legacy_path}?limit=5", allow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"{prompt_path}?limit=5"


@pytest.mark.parametrize(("method", "legacy_path", "prompt_path"), [
    ("get", "/posts-fragment", "/prompts-fragment"),
    ("get", "/users/example-id/posts-fragment", "/users/example-id/prompts-fragment"),
    ("prompt", "/posts", "/prompts"),
    ("patch", "/posts/example-id", "/prompts/example-id"),
    ("prompt", "/posts/example-id/status", "/prompts/example-id/status"),
    ("prompt", "/posts/example-id/impression", "/prompts/example-id/impression"),
    ("prompt", "/posts/example-id/comment", "/prompts/example-id/comment"),
    ("patch", "/posts/example-id/comments/example-comment-id",
     "/prompts/example-id/comments/example-comment-id"),
    ("get", "/post-tags/example-tag/edit", "/tags/example-tag/edit"),
    ("get", "/post-tags", "/tags"),
    ("patch", "/post-tags/example-tag", "/tags/example-tag"),
])
def test_legacy_prompt_endpoint_urls_preserve_method_and_redirect(
        guest_client, method, legacy_path, prompt_path):
    request = {"get": get, "prompt": prompt, "patch": patch}[method]
    kwargs = {"allow_redirects": False}
    if method != "get":
        kwargs["json"] = {}
    response = request(guest_client, f"{legacy_path}?limit=5", **kwargs)
    assert response.status_code == 308
    assert response.headers["location"] == f"{prompt_path}?limit=5"


@pytest.mark.parametrize("path", [
    "/",
    "/prompts",
    "/contacts",
    "/users",
    "/latest/users",
    "/prompts-fragment",
    "/users-fragment",
    "/tags",
    "/tags",
    "/privacy-policy",
    "/rules",
    "/terms-of-service",
    "/earn-with-us",
])
def test_public_read_endpoints_success_and_wrong_method_failure(guest_client, path):
    success = get(guest_client, path)
    assert success.status_code == 200, (path, success.status_code, success.text)

    failure = prompt(guest_client, path, json={})
    expected_status = 422 if path == "/prompts" else 405
    assert failure.status_code == expected_status, (path, failure.status_code, failure.text)


@pytest.mark.parametrize("path, schema_type", [
    ("/", "WebSite"),
    ("/prompts", "CollectionPage"),
    ("/users", "CollectionPage"),
    ("/latest/users", "CollectionPage"),
    ("/contacts", "ContactPage"),
    ("/privacy-policy", "WebPage"),
    ("/rules", "WebPage"),
    ("/terms-of-service", "WebPage"),
    ("/earn-with-us", "WebPage"),
])
def test_public_page_seo_schema_and_metadata(guest_client, path, schema_type):
    response = get(guest_client, path)
    assert response.status_code == 200, (path, response.status_code, response.text)
    doc = pq(response.text)
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == schema_type
    assert schema.get("url", "").startswith("http")
    assert doc('link[rel="canonical"]').attr("href").startswith("http")
    assert doc('meta[name="description"]').attr("content")
    assert doc('meta[name="robots"]').attr("content") in {"index, follow", "noindex, follow", "noindex, nofollow"}
    assert all(value is not None for value in schema.values())
    if schema_type in {"CollectionPage", "ContactPage", "WebPage"}:
        assert schema.get("breadcrumb", {}).get("itemListElement")


@pytest.mark.parametrize("path", [
    "/prompts?limit=invalid",
    "/prompts-fragment?limit=0",
    "/users?type=invalid",
    "/invalid/users",
    "/users-fragment?status=invalid",
    "/tags?prefix=",
])
def test_public_query_endpoints_reject_invalid_parameters(guest_client, path):
    response = get(guest_client, path)
    assert response.status_code == 422, (path, response.status_code, response.text)


def test_tags_fragment_endpoint_success(guest_client):
    response = get(guest_client, "/tags-fragment?type=latest&limit=6")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("tag_type", ["latest", "popular"])
def test_tags_endpoint_supports_tag_types(guest_client, tag_type):
    response = get(guest_client, f"/tags?type={tag_type}&limit=6")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_login_endpoint_success_and_wrong_method_failure(guest_client):
    success = get(guest_client, "/login", allow_redirects=False)
    assert success.status_code in (302, 307)
    assert "location" in success.headers

    failure = prompt(guest_client, "/login", json={})
    assert failure.status_code == 405


def test_login_callback_success_and_invalid_code_failure():
    success_client = get_logged_in_client({
        "sub": "callback-success-sub",
        "iss": "callback-success-iss",
        "email": "callback-success@example.com",
    })
    assert success_client.cookies.get("token")

    failure = get(get_guest_client(), "/login-callback?code=invalid", allow_redirects=False)
    assert failure.status_code == 400


def test_logout_callback_success_and_wrong_method_failure(guest_client):
    success = get(guest_client, "/logout-callback", allow_redirects=False)
    assert success.status_code in (302, 307)

    failure = prompt(guest_client, "/logout-callback", json={})
    assert failure.status_code == 405


functional_state = {}


def test_user_edit_update_and_fragment_endpoints_success_and_failure(root_user_client, guest_client):
    root_user_client = get_logged_in_client(root_user)
    root_id = get_dynamodb_user_by_email(root_user["email"])["id"]
    functional_state["root_id"] = root_id

    edit_success = get(root_user_client, f"/users/{root_id}/edit")
    assert edit_success.status_code == 200
    edit_failure = get(guest_client, f"/users/{root_id}/edit")
    assert edit_failure.status_code == 401

    update_success = patch(root_user_client, f"/users/{root_id}", json={
        "name": "Root Functional User",
        "username": "root-functional",
    })
    assert update_success.status_code == 200, update_success.text
    update_failure = patch(root_user_client, f"/users/{root_id}", json={"name": ""})
    assert update_failure.status_code == 422

    fragment_success = get(guest_client, f"/users/{root_id}/prompts-fragment")
    assert fragment_success.status_code == 200
    user_read_failure = get(guest_client, "/users/missing-user")
    assert user_read_failure.status_code == 404

    fragment_failure = get(guest_client, "/users/missing-user/prompts-fragment")
    assert fragment_failure.status_code == 404

    slug_success = get(guest_client, "/root-functional")
    assert slug_success.status_code == 200
    slug_failure = get(guest_client, "/missing-functional-user")
    assert slug_failure.status_code == 404


def test_user_settings_endpoints_success_and_failure(guest_client):
    root_client = get_logged_in_client(root_user)
    root_id = functional_state["root_id"]
    expected_user_url = get_user_href(get_dynamodb_user(root_id))

    activity_success = patch(root_client, f"/users/{root_id}/activity-settings", json={
        "show_activity_calendar": True,
        "show_recent_activity": True,
    })
    assert activity_success.status_code == 200, activity_success.text
    assert activity_success.json() == expected_user_url

    interests_success = patch(root_client, f"/users/{root_id}/interests-settings", json={
        "show_interests": False,
    })
    assert interests_success.status_code == 200, interests_success.text
    assert interests_success.json() == expected_user_url

    updated_user = get_dynamodb_user(root_id)
    assert updated_user["show_activity_calendar"] is True
    assert updated_user["show_recent_activity"] is True
    assert updated_user["show_interests"] is False

    activity_failure = patch(guest_client, f"/users/{root_id}/activity-settings", json={
        "show_activity_calendar": True,
    })
    assert activity_failure.status_code == 401
    interests_failure = patch(guest_client, f"/users/{root_id}/interests-settings", json={
        "show_interests": True,
    })
    assert interests_failure.status_code == 401


def test_user_impression_endpoint_success_and_validation_failure(regular_user_client):
    regular_user_client = get_logged_in_client(regular_user)
    target_id = get_dynamodb_user_by_email(regular_2_user["email"])["id"]
    success = prompt(regular_user_client, f"/users/{target_id}/impression", json={"action": "follow"})
    assert success.status_code == 200, success.text
    failure = prompt(regular_user_client, f"/users/{target_id}/impression", json={"action": "invalid"})
    assert failure.status_code == 422


def test_user_status_endpoint_success_and_validation_failure(root_user_client):
    root_user_client = get_logged_in_client(root_user)
    target = get_dynamodb_user_by_email("callback-success@example.com")
    success = prompt(root_user_client, f"/users/{target["id"]}/status", json={
        "status": "banned",
        "comment": "Functional test ban",
    })
    assert success.status_code == 200, success.text
    failure = prompt(root_user_client, f"/users/{target["id"]}/status", json={"status": "invalid"})
    assert failure.status_code == 422


PROMPT_IMAGE_FILENAME = "9ba8f5cf-b0a4-430c-99ec-4a78f3c4245f_1080x784.png"
PROMPT_IMAGE_ALT = "Functional prompt image"
PROMPT_CONTENT = ("Functional endpoint coverage content. " * 140
                   + f'<p><img src="/{PROMPT_IMAGE_FILENAME}" alt="{PROMPT_IMAGE_ALT}"></p>')


def test_prompt_create_and_new_page_endpoints_success_and_failure(guest_client):
    root_client = get_logged_in_client(root_user)

    new_success = get(root_client, "/prompts/new")
    assert new_success.status_code == 200
    new_failure = get(guest_client, "/prompts/new")
    assert new_failure.status_code == 401

    create_success = prompt(root_client, "/prompts", json={
        "title": "Functional endpoint coverage prompt",
        "content": PROMPT_CONTENT,
        "tags": ["functional-tag", "coverage-tag"],
        "image_filenames": [PROMPT_IMAGE_FILENAME],
    })
    assert create_success.status_code == 200, create_success.text
    prompt_item = next(
        item for item in dynamodb_table.scan()["Items"]
        if item.get("title") == "Functional endpoint coverage prompt"
    )
    functional_state["prompt_id"] = prompt_item["id"]
    functional_state["prompt_slug"] = prompt_item["prompt_slug"]
    assert prompt_item["content"] == PROMPT_CONTENT
    assert prompt_item["image_filenames"] == [PROMPT_IMAGE_FILENAME]

    create_failure = prompt(root_client, "/prompts", json={
        "title": "short",
        "content": PROMPT_CONTENT,
        "tags": ["functional-tag"],
    })
    assert create_failure.status_code == 422


def test_earn_page_seo(guest_client):
    response = get(guest_client, "/earn-with-us")
    assert response.status_code == 200
    doc = pq(response.text)
    schema = json.loads(doc('script[type="application/ld+json"]').text())
    assert schema["@type"] == "WebPage"
    assert schema["breadcrumb"]["itemListElement"][-1]["name"] == "Earn with us"
    assert doc('meta[name="description"]').attr("content").startswith("Learn how to publish")
    assert doc('link[rel="canonical"]').attr("href").endswith("/earn-with-us")


def test_prompt_read_edit_update_status_endpoints_success_and_failure(guest_client):
    root_client = get_logged_in_client(root_user)
    regular_client = get_logged_in_client(regular_user)
    prompt_id = functional_state["prompt_id"]

    read_success = get(root_client, f"/prompts/{prompt_id}")
    assert read_success.status_code == 200, read_success.text
    read_doc = pq(read_success.text)
    prompt_schema = json.loads(read_doc('script[type="application/ld+json"]').text())
    assert prompt_schema["@type"] == "Prompt"
    assert prompt_schema["inLanguage"] == "en"
    assert prompt_schema["author"]["url"].endswith("/root-functional")
    assert read_doc('meta[property="og:type"]').attr("content") == "prompt"
    assert read_doc('meta[property="og:url"]').attr("content").endswith(
        f"/root-functional/{functional_state['prompt_slug']}")
    assert not read_doc('meta[name="keywords"]')
    assert "aggregateRating" not in prompt_schema
    assert prompt_schema["commentCount"] == 0
    assert prompt_schema["image"][0].endswith(f"/{PROMPT_IMAGE_FILENAME}")
    assert prompt_schema["thumbnailUrl"].endswith(f"/{PROMPT_IMAGE_FILENAME}")
    assert read_doc('meta[name="robots"]').attr("content") == "index, follow"
    rendered_picture = read_doc("prompt picture")
    assert len(rendered_picture) == 1
    rendered_source = rendered_picture("source")
    assert len(rendered_source) == 1
    assert rendered_source.attr("type") == "image/webp"
    assert f"{PROMPT_IMAGE_FILENAME.rsplit('_', 1)[0]}_320x" in rendered_source.attr("srcset")
    assert f"{PROMPT_IMAGE_FILENAME.rsplit('_', 1)[0]}_640x" in rendered_source.attr("srcset")
    assert f"{PROMPT_IMAGE_FILENAME.rsplit('_', 1)[0]}_1024x" in rendered_source.attr("srcset")
    rendered_img = rendered_picture("img")
    assert rendered_img.attr("alt") == "Functional endpoint coverage prompt"
    assert "<figure" in read_success.text

    dynamodb_table.update_item(
        Key={"pk": f"PROMPT#{prompt_id}", "sk": "META"},
        UpdateExpression="SET image_filenames = :filenames",
        ExpressionAttributeValues={":filenames": ["promptcatalog_1161x515.png"]},
    )
    image_doc = pq(get(root_client, f"/prompts/{prompt_id}").text)
    image_schema = json.loads(image_doc('script[type="application/ld+json"]').text())
    assert image_schema["image"][0].endswith("/promptcatalog_1161x515.png")
    assert image_schema["thumbnailUrl"].endswith("/promptcatalog_1161x515.png")
    assert image_doc('meta[property="og:image"]').attr("content").endswith("/promptcatalog_1161x515.png")
    dynamodb_table.update_item(
        Key={"pk": f"PROMPT#{prompt_id}", "sk": "META"},
        UpdateExpression="REMOVE image_filenames",
    )

    read_failure = get(guest_client, "/prompts/missing-prompt")
    assert read_failure.status_code == 404

    edit_success = get(root_client, f"/prompts/{prompt_id}/edit")
    assert edit_success.status_code == 200
    edit_doc = pq(edit_success.text)
    raw_editor_content = edit_doc("textarea.editor").text()
    assert f'<img src="/{PROMPT_IMAGE_FILENAME}" alt="{PROMPT_IMAGE_ALT}">' in raw_editor_content
    assert "<picture>" not in raw_editor_content
    edit_failure = get(regular_client, f"/prompts/{prompt_id}/edit")
    assert edit_failure.status_code == 403

    update_success = patch(root_client, f"/prompts/{prompt_id}", json={
        "title": "Updated functional endpoint coverage prompt",
        "content": PROMPT_CONTENT,
        "tags": ["functional-tag", "coverage-tag"],
    })
    assert update_success.status_code == 200, update_success.text
    functional_state["prompt_slug"] = "updated-functional-endpoint-coverage-prompt"
    update_failure = patch(root_client, f"/prompts/{prompt_id}", json={
        "title": "bad",
        "content": PROMPT_CONTENT,
        "tags": ["functional-tag"],
    })
    assert update_failure.status_code == 422

    status_success = prompt(root_client, f"/prompts/{prompt_id}/status", json={"status": "published"})
    assert status_success.status_code == 200, status_success.text

    published_tag_page = get(guest_client, "/prompts?type=latest&status=published&tags=functional-tag")
    assert published_tag_page.status_code == 200
    assert "Updated functional endpoint coverage prompt" in pq(published_tag_page.text)("#prompts").text()

    remove_tag_success = patch(root_client, f"/prompts/{prompt_id}", json={
        "tags": ["coverage-tag"],
    })
    assert remove_tag_success.status_code == 200, remove_tag_success.text
    removed_tag_page = get(guest_client, "/prompts?type=latest&status=published&tags=functional-tag")
    assert removed_tag_page.status_code == 200
    assert "Updated functional endpoint coverage prompt" not in pq(removed_tag_page.text)("#prompts").text()

    republish_success = prompt(root_client, f"/prompts/{prompt_id}/status", json={"status": "published"})
    assert republish_success.status_code == 200, republish_success.text
    current_tag_page = get(guest_client, "/prompts?type=latest&status=published&tags=coverage-tag")
    assert current_tag_page.status_code == 200
    assert "Updated functional endpoint coverage prompt" in pq(current_tag_page.text)("#prompts").text()
    stale_tag_page = get(guest_client, "/prompts?type=latest&status=published&tags=functional-tag")
    assert stale_tag_page.status_code == 200
    assert "Updated functional endpoint coverage prompt" not in pq(stale_tag_page.text)("#prompts").text()

    restore_tags_success = patch(root_client, f"/prompts/{prompt_id}", json={
        "tags": ["functional-tag", "coverage-tag"],
    })
    assert restore_tags_success.status_code == 200, restore_tags_success.text
    restore_publish_success = prompt(root_client, f"/prompts/{prompt_id}/status", json={"status": "published"})
    assert restore_publish_success.status_code == 200, restore_publish_success.text

    rename_tag_success = patch(root_client, "/tags/coverage-tag", json={
        "name": "Coverage Tag Updated",
        "image_action": "keep",
        "image_file": None,
    })
    assert rename_tag_success.status_code == 200, rename_tag_success.text
    renamed_old_tag_page = get(
        guest_client,
        "/prompts?type=latest&status=published&tags=coverage-tag",
        allow_redirects=False,
    )
    assert renamed_old_tag_page.status_code == 301
    assert "coverage-tag-updated" in renamed_old_tag_page.headers["location"]
    renamed_current_tag_page = get(guest_client, "/prompts?type=latest&status=published&tags=coverage-tag-updated")
    assert renamed_current_tag_page.status_code == 200
    assert "Updated functional endpoint coverage prompt" in pq(renamed_current_tag_page.text)("#prompts").text()

    status_failure = prompt(root_client, f"/prompts/{prompt_id}/status", json={"status": "invalid"})
    assert status_failure.status_code == 422

    slug_success = get(guest_client, f"/root-functional/{functional_state["prompt_slug"]}")
    assert slug_success.status_code == 200, slug_success.text
    slug_failure = get(guest_client, "/root-functional/missing-prompt")
    assert slug_failure.status_code == 404

    prompts_by_slug_success = get(guest_client, "/root-functional/prompts")
    assert prompts_by_slug_success.status_code == 200
    prompts_by_slug_failure = get(guest_client, "/invalid/latest/prompts?limit=0")
    assert prompts_by_slug_failure.status_code == 422


def test_prompt_impression_comment_and_comment_update_endpoints_success_and_failure(guest_client):
    regular_client = get_logged_in_client(regular_user)
    prompt_id = functional_state["prompt_id"]

    impression_success = prompt(regular_client, f"/prompts/{prompt_id}/impression", json={"action": "like"})
    assert impression_success.status_code == 200, impression_success.text
    rated_doc = pq(get(regular_client, f"/prompts/{prompt_id}").text)
    rated_schema = json.loads(rated_doc('script[type="application/ld+json"]').text())
    assert "aggregateRating" not in rated_schema
    assert not rated_doc('meta[name="ratingValue"]')
    assert not rated_doc('meta[name="ratingCount"]')
    impression_failure = prompt(guest_client, f"/prompts/{prompt_id}/impression", json={"action": "like"})
    assert impression_failure.status_code == 401

    comment_text = "Functional endpoint comment"
    comment_success = prompt(regular_client, f"/prompts/{prompt_id}/comment", json={"text": comment_text})
    assert comment_success.status_code == 200, comment_success.text
    comment_item = next(
        item for item in dynamodb_table.scan()["Items"]
        if item.get("prompt_id") == prompt_id and item.get("text") == comment_text
    )
    comment_id = comment_item["id"]
    encoded_comment_id = quote(comment_id, safe="")
    functional_state["comment_id"] = comment_id
    comment_failure = prompt(regular_client, f"/prompts/{prompt_id}/comment", json={"text": ""})
    assert comment_failure.status_code == 422

    update_success = patch(regular_client, f"/prompts/{prompt_id}/comments/{encoded_comment_id}", json={
        "text": "Updated functional endpoint comment",
    })
    assert update_success.status_code == 200, update_success.text
    update_failure = patch(regular_client, f"/prompts/{prompt_id}/comments/missing-comment", json={
        "text": "Still valid text",
    })
    assert update_failure.status_code == 404

    comments_doc = pq(get(regular_client, f"/prompts/{prompt_id}").text)
    comments_schema = json.loads(comments_doc('script[type="application/ld+json"]').text())
    assert comments_schema["commentCount"] == 1
    assert len(comments_schema["comment"]) == 1
    assert comments_schema["comment"][0]["text"] == "Updated functional endpoint comment"
    comment_id_fragment = comments_schema["comment"][0]["@id"].rsplit("#", 1)[-1]
    assert comments_doc(f"prompt#{comment_id_fragment}")
    assert comments_doc(f'time[datetime="{comments_schema["comment"][0]["datePublished"]}"]')

    comments_fragment = get(regular_client, f"/prompts/{prompt_id}/comments-fragment?limit=1")
    assert comments_fragment.status_code == 200, comments_fragment.text
    assert "Updated functional endpoint comment" in comments_fragment.text
    assert "prompt-comment" in comments_fragment.text
    missing_fragment = get(guest_client, "/prompts/missing-prompt/comments-fragment")
    assert missing_fragment.status_code == 404


def test_public_file_upload_endpoint_success_and_failure(guest_client):
    png_content = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 1100)
    success = prompt(guest_client, "/public-file", files={
        "file": ("functional.png", png_content, "image/png"),
    })
    assert success.status_code == 200, success.text
    uploaded_path = os.path.join("/app/static", success.json())
    os.remove(uploaded_path)

    failure = prompt(guest_client, "/public-file", files={
        "file": ("invalid.txt", b"not an image" * 100, "text/plain"),
    })
    assert failure.status_code == 422
    assert failure.headers["content-type"].startswith("application/json")
    assert failure.json()["details"]["file"] == "Invalid image type: None"


def test_contact_message_endpoint_success_and_validation_failure(guest_client):
    success = prompt(guest_client, "/contacts/message", json={
        "name": "Functional Contact",
        "email": "functional-contact@example.com",
        "message": "Functional contact message",
    })
    assert success.status_code == 204, success.text

    failure = prompt(guest_client, "/contacts/message", json={
        "name": "X",
        "email": "invalid",
        "message": "bad",
    })
    assert failure.status_code == 422


def test_tag_edit_and_update_endpoints_success_and_failure():
    root_client = get_logged_in_client(root_user)
    regular_client = get_logged_in_client(regular_user)

    edit_success = get(root_client, "/tags/functional-tag/edit")
    assert edit_success.status_code == 200, edit_success.text
    edit_failure = get(regular_client, "/tags/functional-tag/edit")
    assert edit_failure.status_code == 403

    update_success = patch(root_client, "/tags/functional-tag", json={
        "name": "Functional Tag Updated",
        "image_action": "keep",
        "image_file": None,
    })
    assert update_success.status_code == 200, update_success.text
    update_failure = patch(root_client, "/tags/functional-tag-updated", json={
        "name": "X",
        "image_action": "keep",
    })
    assert update_failure.status_code == 422


def test_admin_page_sitemap_and_cache_endpoints_success_and_failure(guest_client):
    root_client = get_logged_in_client(root_user)
    regular_client = get_logged_in_client(regular_user)

    utils_success = get(root_client, "/utils")
    assert utils_success.status_code == 200
    utils_failure = get(guest_client, "/utils")
    assert utils_failure.status_code == 401

    sitemap_success = prompt(root_client, "/generate-sitemap", json={})
    assert sitemap_success.status_code == 200, sitemap_success.text
    assert sitemap_success.json()["urls_count"] > 0
    sitemap = get(guest_client, "/sitemap.xml")
    assert sitemap.status_code == 200
    assert "/tags" in sitemap.text
    assert "/functional-tag-updated/prompts" in sitemap.text
    assert "/popular/functional-tag-updated/prompts" in sitemap.text
    assert "/Functional Tag Updated/prompts" not in sitemap.text
    sitemap_failure = prompt(regular_client, "/generate-sitemap", json={})
    assert sitemap_failure.status_code == 403

    cache_success = prompt(root_client, "/drop-cdn-cache", json={})
    assert cache_success.status_code == 200, cache_success.text
    assert cache_success.json()["success"] is True
    cache_failure = prompt(regular_client, "/drop-cdn-cache", json={})
    assert cache_failure.status_code == 403


def test_tag_subscription_create_and_delete():
    root_user_client = get_logged_in_client(root_user)
    tags = ["lifecycle-tag", "lifecycle-combination"]
    response = prompt(root_user_client, "/tag-subscriptions", json={"tags": tags})
    assert response.status_code == 200, response.text

    fragment = pq(response.text)
    subscription_id = fragment(".tag-subscription-block").attr("data-tag-subscription-id")
    assert subscription_id
    assert "Subscribed" in response.text

    subscriptions = get(root_user_client, "/tag-subscriptions")
    assert subscriptions.status_code == 200
    assert any(item["id"] == subscription_id and item["tags"] == sorted(tags)
               for item in subscriptions.json())

    delete_response = delete(root_user_client, f"/tag-subscriptions/{subscription_id}")
    assert delete_response.status_code == 200, delete_response.text
    assert pq(delete_response.text)(".tag-subscription-block").attr("data-tag-subscription-id") == ""
    assert "Subscribed" not in delete_response.text

    subscriptions = get(root_user_client, "/tag-subscriptions")
    assert all(item["id"] != subscription_id for item in subscriptions.json())


def test_prompt_published_dispatch_matches_combinations_excludes_author_and_renders_eml():
    root_client = get_logged_in_client(root_user)
    set_dynamodb_user_permissions(get_logged_in_user_id(root_user), ["root"])
    author_client = get_logged_in_client(regular_user)
    combination_client = get_logged_in_client(regular_2_user)
    email_dir = Path("/app/.emails")
    existing_emails = set(email_dir.glob("*.eml"))

    root_subscription = prompt(root_client, "/tag-subscriptions", json={
        "tags": ["notification-tag3"],
    })
    assert root_subscription.status_code == 200, root_subscription.text
    author_subscription = prompt(author_client, "/tag-subscriptions", json={
        "tags": ["notification-tag1"],
    })
    assert author_subscription.status_code == 200, author_subscription.text
    combination_subscription = prompt(combination_client, "/tag-subscriptions", json={
        "tags": ["notification-tag2", "notification-tag3"],
    })
    assert combination_subscription.status_code == 200, combination_subscription.text

    create_response = prompt(author_client, "/prompts", json={
        "title": "Combination notification integration prompt",
        "content": PROMPT_CONTENT,
        "tags": ["notification-tag1", "notification-tag2", "notification-tag3"],
    })
    assert create_response.status_code == 200, create_response.text
    prompt_id = create_response.json().rstrip("/").split("/")[-1]

    publish_response = prompt(root_client, f"/prompts/{prompt_id}/status", json={
        "status": "published",
    })
    assert publish_response.status_code == 200, publish_response.text

    new_emails = sorted(set(email_dir.glob("*.eml")) - existing_emails)
    assert len(new_emails) == 2
    messages = {}
    for email_file in new_emails:
        with email_file.open("rb") as stream:
            message = BytesParser(policy=policy.default).parse(stream)
        messages[message["To"]] = message

    assert set(messages) == {"root@example.com", "regular2@example.com"}
    assert "regular@example.com" not in messages

    root_html = messages["root@example.com"].get_body("html").get_content()
    assert f"Hello {get_dynamodb_user_by_email('root@example.com')['name']}" in root_html
    assert "notification-tag3" in root_html
    assert "tags=notification-tag3" in root_html
    assert "notification-tag2 + notification-tag3" not in root_html
    assert "Best regards" in root_html

    combination_html = messages["regular2@example.com"].get_body("html").get_content()
    assert "notification-tag2 + notification-tag3" in combination_html
    assert "tags=notification-tag2&amp;tags=notification-tag3" in combination_html
    assert "Read prompt" in combination_html


def test_logout_endpoint_wrong_method_failure(guest_client):
    failure = prompt(guest_client, "/logout", json={})
    assert failure.status_code == 405
