"""Canonical web route names and path templates."""

WEB_AUTH_URL_ROUTES = {
    "login": "/login",
    "login-callback": "/login-callback",
    "logout": "/logout",
    "logout-callback": "/logout-callback",
}

WEB_URL_ROUTES = WEB_AUTH_URL_ROUTES | {
    "index": "/",
    "static-file": "/{filename:path}",
    "new-prompt": "/prompts/new",
    "prompts": "/prompts",
    "tags": "/tags",
    "categories": "/categories",
    "edit-category": "/categories/{slug}/edit",
    "prompt": "/prompts/{prompt_id}",
    "edit-prompt": "/prompts/{prompt_id}/edit",
    "prompts-by-slugs": "/{slugs_path:path}/prompts",
    "contacts": "/contacts",
    "edit-tag": "/tags/{slug}/edit",
    "users": "/users",
    "users-by-slugs": "/{type}/users",
    "user": "/users/{user_id}",
    "edit-user": "/users/{user_id}/edit",
    "policy": "/privacy-policy",
    "rules": "/rules",
    "terms": "/terms-of-service",
    "earn": "/earn-with-us",
    "utils": "/utils",
    "user-by-slug": "/@{slug}",
    "prompt-by-slugs": "/@{user_slug}/{prompt_slug}",
    "legacy-user-by-slug": "/{slug}",
}
