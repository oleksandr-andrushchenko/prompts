import threading
import time
from datetime import timedelta
from urllib.parse import quote, urlparse

from shared_utils import *
from shared_utils import (
    Prompt, PromptStatus, PromptQueryType, PromptNotFoundError,
    PromptByOldSlugRequestedError, User, UserStatus, UserNotFoundError,
    UserByOldSlugRequestedError, NotAuthenticatedError, Permission,
    find_prompt_by_slug_follow_redirects, find_user_by_username_follow_redirects,
    verify_authorization, get_prompt_url, get_user_url, get_web_base_url, is_prod,
    get_auth_token_max_age, get_dynamodb_table, prompt_from_dynamodb,
    query_dynamodb_table, Key, to_thread, get_config,
)

THREADS_API_BASE = "https://graph.threads.net"
THREADS_FIELDS = "id,media_type,permalink,username,text,timestamp,alt_text"
THREADS_RESULTS_LIMIT = 12
THREADS_TAG_LIMIT = 3
_threads_cache: dict[tuple[str, str], tuple[float, list[dict[str, str | None]]]] = {}
_threads_request_lock = threading.Lock()
_threads_last_request_at = 0.0


def _safe_threads_permalink(value) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
            hostname == "threads.net" or hostname.endswith(".threads.net")):
        return None
    return value


def _normalize_threads_post(value: dict, matched_tag: str) -> dict[str, str | None] | None:
    permalink = _safe_threads_permalink(value.get("permalink"))
    item_id = value.get("id")
    if not permalink or not isinstance(item_id, str) or not item_id:
        return None
    return {
        "id": item_id,
        "username": value.get("username") if isinstance(value.get("username"), str) else None,
        "text": value.get("text") if isinstance(value.get("text"), str) else None,
        "timestamp": value.get("timestamp") if isinstance(value.get("timestamp"), str) else None,
        "media_type": value.get("media_type") if isinstance(value.get("media_type"), str) else None,
        "alt_text": value.get("alt_text") if isinstance(value.get("alt_text"), str) else None,
        "permalink": permalink,
        "matched_tag": matched_tag,
    }


def _get_threads_posts_for_tag(
        tag: str,
        search_type: str,
        token: str,
) -> list[dict[str, str | None]]:
    global _threads_last_request_at

    cache_key = (tag.casefold(), search_type)
    now = time.monotonic()
    cache_seconds = max(30.0, float(get_config().get("threads_cache_seconds", 300)))
    cached = _threads_cache.get(cache_key)
    if cached and now - cached[0] < cache_seconds:
        return cached[1]

    request_delay = max(
        0.0,
        float(get_config().get("threads_request_delay_seconds", 1)),
    )
    with _threads_request_lock:
        remaining = request_delay - (time.monotonic() - _threads_last_request_at)
        if remaining > 0:
            time.sleep(remaining)
        _threads_last_request_at = time.monotonic()
        import httpx
        response = httpx.get(
            f"{THREADS_API_BASE}/keyword_search",
            params={
                "q": tag,
                "search_mode": "KEYWORD",
                "search_type": search_type,
                "fields": THREADS_FIELDS,
                "limit": THREADS_RESULTS_LIMIT,
            },
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "PromptCatalog/1.0",
            },
            timeout=10.0,
            follow_redirects=True,
        )

    if response.status_code in {401, 403}:
        raise PermissionError("Threads rejected the configured credentials or permissions")
    if response.status_code == 429:
        raise RuntimeError("Threads search is temporarily rate limited")
    response.raise_for_status()
    payload = response.json()
    values = payload.get("data") or []
    if not isinstance(values, list):
        raise ValueError("Threads returned an invalid search response")
    posts = []
    for value in values:
        if isinstance(value, dict) and (post := _normalize_threads_post(value, tag)):
            posts.append(post)
    _threads_cache[cache_key] = (time.monotonic(), posts)
    return posts


def get_hot_threads_posts(
        tags: list[str],
        search_type: str,
) -> tuple[list[dict[str, str | None]], str | None]:
    token = get_config().get("threads_access_token")
    if not token:
        return [], "Threads search is not configured."

    unique_tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))[:THREADS_TAG_LIMIT]
    if not unique_tags:
        return [], "Select at least one tag to search Threads."

    posts = []
    seen_ids = set()
    try:
        for tag in unique_tags:
            for post in _get_threads_posts_for_tag(tag, search_type, token):
                if post["id"] in seen_ids:
                    continue
                seen_ids.add(post["id"])
                posts.append(post)
                if len(posts) >= THREADS_RESULTS_LIMIT:
                    return posts, None
    except (PermissionError, RuntimeError, ValueError) as error:
        logger.warning("Threads search unavailable: %s", error)
        return [], "Threads results are temporarily unavailable."
    except Exception:
        logger.exception("Unexpected Threads search failure")
        return [], "Threads results are temporarily unavailable."
    return posts, None


def get_login_redirect_url(callback_url: str) -> str:
    if is_prod():
        return (
            f"https://{get_cognito_domain()}/oauth2/authorize"
            f"?client_id={get_cognito_client_id()}"
            f"&response_type=code"
            f"&redirect_uri={quote(callback_url, safe='')}"
            f"&scope=openid+email+profile"
        )

    return callback_url


def get_user_token_by_code(code: str, callback_url: str) -> UserTokenDTO:
    if is_prod():
        if not code:
            raise InvalidCodeError("Missing code")

        token_url = f"https://{get_cognito_domain()}/oauth2/token"
        cognito_client_id = get_cognito_client_id()
        cognito_client_secret = get_cognito_client_secret()
        data = {
            "grant_type": "authorization_code",
            "client_id": cognito_client_id,
            "code": code,
            "redirect_uri": callback_url,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + base64.b64encode(
                f"{cognito_client_id}:{cognito_client_secret}".encode()
            ).decode()
        }

        import httpx
        with httpx.Client() as client:
            token_resp = client.post(token_url, data=data, headers=headers)
            if token_resp.status_code != 200:
                logger.error(f"Token exchange failed: {token_resp.status_code} {token_resp.text}")
                raise CodeExchangeFailedError("Failed to exchange code")
            tokens = token_resp.json()
            # logger.debug(f"Cognito token response: {tokens}")

        id_token = tokens.get("id_token")
        if not id_token:
            raise InvalidTokenError("Missing id_token in Cognito response")
        from jose import jwt
        claims = jwt.get_unverified_claims(id_token)
        if claims.get("token_use") != "id":
            raise InvalidTokenError(f"Unexpected token_use: {claims.get('token_use')}")

        tokens = {"id_token": id_token}
        user_token = user_token_from_jwt_claims(claims, encode_offset(tokens))
    else:
        try:
            token_args = decode_offset(code) if code else {}
        except (ValueError, UnicodeError) as exc:
            raise InvalidCodeError("Invalid code") from exc
        user_token = get_dummy_user_token(**token_args)

    upsert_user_by_user_token(user_token)
    return user_token


def create_auth_jwt_token(token: UserTokenDTO) -> str:
    expires_in = get_auth_token_max_age()

    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=expires_in)

    from jose import jwt
    return jwt.encode(
        claims={
            "sub": token.sub,
            "iss": "internal_auth",
            "origin_iss": token.iss,
            "sid": uuid.uuid4().hex,
            "email": token.email,
            "name": token.name,
            "username": token.username,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "type": "auth_token",
            "aud": "prompts",
            "origin_aud": token.aud,
        },
        key=get_auth_jwt_secret(),
        algorithm="HS256"
    )


def get_logout_redirect_url(callback_url: str) -> str:
    if is_prod():
        return (
            f"https://{get_cognito_domain()}/logout"
            f"?client_id={get_cognito_client_id()}"
            # f"&response_type=code"
            f"&logout_uri={quote(callback_url, safe='')}"
            # f"&scope=openid+email+profile"
        )

    return callback_url


def get_redirect_url(req) -> str:
    redirect_url = req.query_params.get("redirect_url")

    if not redirect_url:
        referer = req.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            base_url = urlparse(get_web_base_url())

            # If referer has no netloc (relative path) → safe
            # If referer belongs to your domain → safe
            if not parsed.netloc or parsed.netloc == base_url.netloc:
                redirect_url = referer

    if not redirect_url:
        redirect_url = get_url(req, "index")

    return redirect_url


def get_user_activities(user: User, year: int | None = None, recent_limit: int = 10) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if year is None:
        # Show the current calendar month plus the preceding 11 months.
        month_index = now.year * 12 + (now.month - 1) - 11
        start_year, start_month = divmod(month_index, 12)
        start = datetime(start_year, start_month + 1, 1, tzinfo=timezone.utc)
        end, calendar_year = now, None
    else:
        if year < 1970 or year > now.year:
            raise ValueError("invalid activity year")
        start, end, calendar_year = datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1,
                                                                                        tzinfo=timezone.utc), year
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    activities = []
    if user.published_prompts_count or user.prompt_comments_count:
        resp = query_dynamodb_table(
            key_condition_expr=Key("pk").eq(f"USER_ACTIVITY#{user.id}") & Key("sk").between(
                f"ACTIVITY#{start_ms}", f"ACTIVITY#{end_ms}#~"
            ),
            scan_index_forward=False,
            limit=1000,
        )
        activities = [
            user_activity_from_dynamodb(item)
            for item in resp.get("Items", [])
            if item.get("profile_visible")
        ]
    counts = {}
    for activity in activities:
        day = datetime.fromtimestamp(float(activity.created_at) / 1000, tz=timezone.utc).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    first_day = start.date()
    last_day = (end - timedelta(milliseconds=1)).date()
    calendar_days = []
    cursor = first_day
    while cursor <= last_day:
        key = cursor.isoformat()
        calendar_days.append({"date": key, "count": counts.get(key, 0)})
        cursor += timedelta(days=1)
    months = []
    for day in calendar_days:
        month_key = day["date"][:7]
        if not months or months[-1]["key"] != month_key:
            month_date = datetime.strptime(month_key, "%Y-%m")
            months.append({"key": month_key, "label": month_date.strftime("%b"), "days": []})
        months[-1]["days"].append(day)
    for month in months:
        first = datetime.strptime(month["key"], "%Y-%m").date()
        leading = (first.weekday() + 1) % 7
        cells = [{"date": None, "count": 0}] * leading + month["days"]
        while len(cells) % 7:
            cells.append({"date": None, "count": 0})
        month["weeks"] = [cells[index:index + 7] for index in range(0, len(cells), 7)]
        month["week_count"] = len(month["weeks"])
        while len(month["weeks"]) < 6:
            month["weeks"].append([{"date": None, "count": 0} for _ in range(7)])
    return {
        "year": calendar_year,
        "current_year": now.year,
        "total": len(activities),
        "days": counts,
        "calendar_days": calendar_days,
        "months": months,
        "recent": activities[:recent_limit]
    }


def get_latest_published_prompts(limit: int = BaseQueryDTO.DEFAULT_LIMIT) -> list[Prompt]:
    query_dto = PromptQueryDTO(limit=limit)
    return get_latest_prompts(query_dto)


def should_show_popular_prompts(latest_prompts: list[Prompt], popular_prompts: list[Prompt]) -> bool:
    """
    Show popular posts only if popular_posts differ from latest_posts.
    Comparison is based on post IDs.
    """
    latest_ids = [prompt.id for prompt in latest_prompts]
    popular_ids = [prompt.id for prompt in popular_prompts]

    # Show popular posts only if the lists are not exactly equal
    return latest_ids != popular_ids


def get_popular_published_prompts(limit: int = BaseQueryDTO.DEFAULT_LIMIT) -> list[Prompt]:
    query_dto = PromptQueryDTO(limit=limit)
    return get_popular_prompts(query_dto)


def _get_prompt_ids_by_tag(tag: str, limit: int) -> list[str]:
    response = query_dynamodb_table(
        key_condition_expr=Key("pk").eq(f"TAG_COMBO#{tag}"),
        scan_index_forward=False,
        limit=limit,
    )
    return [item["prompt_id"] for item in response.get("Items", []) if item.get("prompt_id")]


def _get_prompts_by_ids(prompt_ids: list[str]) -> list[Prompt]:
    if not prompt_ids:
        return []

    table = get_dynamodb_table()
    keys = [{"pk": f"PROMPT#{prompt_id}", "sk": "META"} for prompt_id in prompt_ids]
    items = []
    batch_size = 100
    max_attempts = 3

    for start in range(0, len(keys), batch_size):
        pending_keys = keys[start:start + batch_size]
        for _ in range(max_attempts):
            response = table.meta.client.batch_get_item(
                RequestItems={table.name: {"Keys": pending_keys}}
            )
            items.extend(response.get("Responses", {}).get(table.name, []))
            pending_keys = response.get("UnprocessedKeys", {}).get(table.name, {}).get("Keys", [])
            if not pending_keys:
                break
        if pending_keys:
            logger.warning("Related prompt batch read left unprocessed keys")

    return [prompt_from_dynamodb(item) for item in items]


async def get_prompt_related_prompts(prompt: Prompt, limit: int = 10) -> list[Prompt]:
    if not prompt.tags:
        return []

    # Single-tag partitions contain small prompt-ID records. Query them in
    # parallel, then batch-load only this bounded candidate set instead of
    # scanning the global full-prompt popularity index.
    per_tag_limit = limit + 1
    prompt_ids_by_tag = await asyncio.gather(*(
        to_thread(_get_prompt_ids_by_tag, tag, per_tag_limit)
        for tag in prompt.tags
    ))
    prompt_ids = list(dict.fromkeys(
        prompt_id
        for tag_prompt_ids in prompt_ids_by_tag
        for prompt_id in tag_prompt_ids
        if prompt_id != prompt.id
    ))
    prompts = await to_thread(_get_prompts_by_ids, prompt_ids)
    tags = set(prompt.tags)
    return sorted(
        (candidate for candidate in prompts
         if candidate.id != prompt.id and candidate.status == PromptStatus.PUBLISHED),
        key=lambda candidate: (len(tags.intersection(candidate.tags)), candidate.rating),
        reverse=True,
    )[:limit]


def get_latest_prompt_comments(query_dto: PromptCommentQueryDTO = None) -> list[PromptComment]:
    if query_dto is None:
        query_dto = PromptCommentQueryDTO()

    return query_dynamodb_items(
        query_dto=query_dto,
        index_name="PROMPT_COMMENTS_BY_CREATED_AT",
        key_condition_expr=Key("prompt_comment_pk").eq("PROMPT_COMMENT"),
        map_fn=prompt_comment_from_dynamodb,
    )


def get_popular_active_users(limit: int = BaseQueryDTO.DEFAULT_LIMIT) -> list[User]:
    query_dto = UserQueryDTO(limit=limit)
    return get_popular_users(query_dto)


def parse_prompts_url_slugs_path(slugs_path: str) -> dict:
    data = {}
    slugs = [p for p in slugs_path.split("/") if p]

    if not slugs:
        return {}

    try:
        data["type"] = PromptQueryType(slugs[0])
        slugs = slugs[1:]
    except ValueError:
        pass

    data["tags"] = slugs

    return data


def get_prompt_by_slugs(user_slug: str, prompt_slug: str, cur_user: User = None) -> Prompt:
    user = find_user_by_username_follow_redirects(user_slug)
    if user is None:
        raise UserNotFoundError(f"User '{user_slug}' not found")
    prompt = find_prompt_by_slug_follow_redirects(user.id, prompt_slug)
    if prompt is None:
        raise PromptNotFoundError(f"Prompt '{prompt_slug}' not found")
    if user.username != user_slug or prompt.user_slug != user.username:
        raise UserNotFoundError(f"User '{user_slug}' not found")
    if prompt.status != PromptStatus.PUBLISHED:
        if not cur_user:
            raise NotAuthenticatedError()
        verify_authorization(cur_user, Permission.READ_NON_PUBLISHED_PROMPT, prompt)
    if prompt.slug != prompt_slug:
        raise PromptByOldSlugRequestedError(prompt_slug, prompt)
    return prompt


def get_user_by_slug(username: str, cur_user: User = None) -> User:
    user = find_user_by_username_follow_redirects(username)
    if user is None:
        raise UserNotFoundError(f"User '{username}' not found")
    if user.status != UserStatus.ACTIVE:
        if not cur_user:
            raise NotAuthenticatedError()
        verify_authorization(cur_user, Permission.READ_NON_ACTIVE_USER, user)
    if user.username != username:
        raise UserByOldSlugRequestedError(username, user)
    return user


def get_legacy_user_redirect_url(req, slug: str) -> str | None:
    user = find_user_by_username_follow_redirects(slug)
    return get_user_url(req, user) if user else None


def get_legacy_prompt_redirect_url(req, user_slug: str, prompt_slug: str) -> str | None:
    user = find_user_by_username_follow_redirects(user_slug)
    if not user:
        return None
    prompt = find_prompt_by_slug_follow_redirects(user.id, prompt_slug)
    if not prompt or prompt.user_slug != user.username:
        return None
    return get_prompt_url(req, prompt)


def _auth_cookie_domain() -> str | None:
    hostname = urlparse(get_web_base_url()).hostname
    if not hostname or hostname in {"localhost", "127.0.0.1"} or "." not in hostname:
        return None
    return f".{hostname}"


def set_token_cookie(token, response):
    response.delete_cookie("token")
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=is_prod(),
        domain=_auth_cookie_domain(),
        samesite="lax",
        max_age=get_auth_token_max_age(),
    )


def drop_token_cookie(response):
    response.delete_cookie("token")
    response.delete_cookie("token", domain=_auth_cookie_domain())
