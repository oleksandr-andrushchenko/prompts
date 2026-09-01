import asyncio

from starlette.exceptions import HTTPException as StarletteHTTPException

from deps import (
    OptCurUserDep,
    ImageFileDTODep,
    CurUserDep,
    PromptQueryDep,
    PromptCommentQueryDep,
    PromptDep,
    TagQueryDep,
    UserQueryDep,
    UserDep,
    UpdateUserDTODep,
    UpdateUserActivitySettingsDTODep,
    UpdateUserInterestsSettingsDTODep,
    get_error_response,
    UpdatePromptDTODep,
    UpdatePromptStatusDTODep,
    UpdatePromptImpressionDTODep,
    UpdateUserImpressionDTODep,
    UpdateUserStatusDTODep,
    PromptCommentDep,
    UpdatePromptCommentDTODep,
    TagDep,
    UpdateTagDTODep,
    TagSubscriptionDTODep,
)
from api_utils import (
    to_thread,
    ContactMessageDTO,
    PromptDTO,
    PromptQueryDTO,
    PromptCommentDTO,
    Tag,
    SlugDuplicationError,
    NotAuthorizedError,
    PromptByOldSlugRequestedError,
    TagByOldSlugRequestedError,
    UserByOldSlugRequestedError,
    UserNotFoundError,
    logger,
    get_html_content,
    get_url,
    get_prompt_url,
    create_prompt,
    create_contact_message,
    update_prompt_status,
    get_users,
    get_latest_prompts_by_user,
    get_prompts,
    find_user,
    jinja2_env,
    update_user,
    update_user_activity_settings,
    update_user_interests_settings,
    update_prompt,
    find_prompt_impression,
    update_prompt_impression,
    update_user_impression,
    find_user_impression,
    get_user_url,
    NotAuthenticatedError,
    update_user_status,
    UserBannedError,
    get_allowed_origins,
    find_prompt,
    create_prompt_comment,
    get_prompt_comments,
    update_prompt_comment,
    get_prompt_comment_url,
    get_tag_url,
    update_tag,
    get_user_tag_subscriptions,
    create_tag_subscription,
    delete_tag_subscription,
)
from shared_utils import (
    find_tag,
    get_tags,
)

from web import Application, Request, HTTPException, HTMLResponse, JSONResponse, RedirectResponse, \
    RequestValidationError, CORSMiddleware

app = Application()

from api_route_metadata import API_URL_ROUTES


def route(method, name, **kwargs):
    return getattr(app, method)(API_URL_ROUTES[name], name=name, **kwargs)


from web_route_metadata import WEB_URL_ROUTES

for _name, _path in WEB_URL_ROUTES.items():
    app.add_url_route(_path, _name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def redirect_legacy_api_endpoints(request: Request, call_next):
    path = request.url.path
    replacements = (
        ("/posts", "/prompts"),
        ("/post-tags", "/tags"),
    )
    for old, new in replacements:
        # In the combined local test app, GET /prompts belongs to the web
        # Lambda; API legacy writes still use the redirect below.
        if old == "/prompts" and request.method == "GET":
            continue
        if old in path:
            path = path.replace(old, new, 1)
            url = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(url=url, status_code=308)
    return await call_next(request)


@app.middleware("http")
async def add_no_robots_to_api(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.middleware("http")
async def inject_template_global_vars(request: Request, call_next):
    jinja2_env().globals["request"] = request
    return await call_next(request)


@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.error(f"HTTP exception: {str(exc)}")
    return get_error_response(request, exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation failed: {str(exc)}")
    details = {}
    for error in exc.errors():
        field = error["loc"][-1] if len(error["loc"]) > 1 else error["loc"][0]
        details[field] = error["msg"]
    return get_error_response(request, 422, details)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_error_handler(request: Request, exc: NotAuthenticatedError):
    logger.error(f"Not authenticated: {str(exc)}")
    return get_error_response(request, 401)


@app.exception_handler(UserBannedError)
async def user_banned_error_handler(request: Request, exc: UserBannedError):
    raise NotAuthorizedError("BANNED")


@app.exception_handler(NotAuthorizedError)
async def not_authorized_error_handler(request: Request, exc: NotAuthorizedError):
    logger.error(f"Not authorized: {str(exc)}")
    return get_error_response(request, 403, {"permission": exc.permission})


@app.exception_handler(PromptByOldSlugRequestedError)
async def prompt_redirect_exception_handler(request: Request, exc: PromptByOldSlugRequestedError):
    logger.info(f"Redirect: {str(exc.slug)} -> {exc.prompt.slug}")
    url = get_prompt_url(request, exc.prompt)
    return RedirectResponse(url=url, status_code=301)


@app.exception_handler(UserByOldSlugRequestedError)
async def prompt_redirect_exception_handler(request: Request, exc: UserByOldSlugRequestedError):
    logger.info(f"Redirect: {str(exc.slug)} -> {exc.user.username}")
    url = get_user_url(request, exc.user)
    return RedirectResponse(url=url, status_code=301)


@app.exception_handler(TagByOldSlugRequestedError)
async def tag_redirect_exception_handler(request: Request, exc: TagByOldSlugRequestedError):
    logger.info(f"Redirect: {str(exc.slug)} -> {exc.tag.slug}")
    if request.url.path.startswith("/tags/"):
        url = get_url(request, "edit-tag", slug=exc.tag.slug)
    else:
        url = get_tag_url(request, exc.tag)
    return RedirectResponse(url=url, status_code=301)


@route("prompt", "upload-public-file", response_class=JSONResponse)
async def upload_public_file(image_file_dto: ImageFileDTODep) -> str:
    from api_utils import save_public_file

    return save_public_file(image_file_dto)


@route("prompt", "create-prompt", response_class=JSONResponse)
async def _create_prompt(prompt_dto: PromptDTO, cur_user: CurUserDep, request: Request) -> str:
    try:
        prompt = create_prompt(prompt_dto, cur_user)
        return get_prompt_url(request, prompt)
    except SlugDuplicationError as e:
        raise HTTPException(status_code=409, detail=e.to_dict())


@route("get", "prompts-fragment", response_class=HTMLResponse)
async def prompts_fragment(query_dto: PromptQueryDep, cur_user: OptCurUserDep) -> str:
    return get_html_content("fragments/prompts.html", {
        "prompts": get_prompts(query_dto, cur_user)
    })


@route("get", "prompt-comments-fragment", response_class=HTMLResponse)
async def prompt_comments_fragment(prompt: PromptDep, query_dto: PromptCommentQueryDep) -> str:
    return get_html_content("fragments/prompt-comments.html", {
        "comments": get_prompt_comments(prompt, query_dto)
    })


@route("patch", "update-prompt", response_class=JSONResponse)
async def _update_prompt(prompt: PromptDep, update_prompt_dto: UpdatePromptDTODep, cur_user: CurUserDep,
                          request: Request) -> str:
    try:
        update_prompt(prompt, update_prompt_dto, cur_user, request)
        return get_prompt_url(request, prompt)
    except SlugDuplicationError as e:
        raise HTTPException(status_code=409, detail=e.to_dict())


@route("prompt", "update-prompt-status", response_class=JSONResponse)
async def _update_prompt_status(prompt: PromptDep, update_prompt_status_dto: UpdatePromptStatusDTODep,
                                 cur_user: CurUserDep, request: Request) -> str:
    update_prompt_status(prompt, update_prompt_status_dto, cur_user, request)
    return get_prompt_url(request, prompt)


@route("prompt", "update-prompt-impression", response_class=HTMLResponse)
async def _update_prompt_impression(prompt: PromptDep, update_prompt_impression_dto: UpdatePromptImpressionDTODep,
                                     cur_user: CurUserDep, request: Request) -> str:
    update_prompt_impression(prompt, update_prompt_impression_dto, cur_user, request)
    (
        prompt,
        prompt_impression,
    ) = await asyncio.gather(
        to_thread(find_prompt, prompt.id),
        to_thread(find_prompt_impression, prompt, cur_user),
    )
    return get_html_content("fragments/prompt-impressions.html", {
        "prompt": prompt,
        "prompt_impression": prompt_impression,
        "cur_user": cur_user,
    })


@route("prompt", "create-prompt-comment", response_class=JSONResponse)
async def _create_prompt_comment(prompt: PromptDep, prompt_comment_dto: PromptCommentDTO, cur_user: CurUserDep,
                                  request: Request) -> str:
    prompt_comment = create_prompt_comment(prompt, prompt_comment_dto, cur_user, request)
    return get_prompt_comment_url(request, prompt, prompt_comment)


@route("patch", "update-prompt-comment",
       response_class=JSONResponse)
async def _update_prompt_comment(prompt: PromptDep, prompt_comment: PromptCommentDep,
                                  update_prompt_comment_dto: UpdatePromptCommentDTODep, cur_user: CurUserDep,
                                  request: Request) -> str:
    update_prompt_comment(prompt, prompt_comment, update_prompt_comment_dto, cur_user, request)
    return get_prompt_comment_url(request, prompt, prompt_comment)


@route("prompt", "create-contact-message", status_code=204)
async def _create_contact_message(message_dto: ContactMessageDTO, cur_user: OptCurUserDep) -> None:
    create_contact_message(message_dto, cur_user)


@route("get", "get-tag-subscriptions", response_class=JSONResponse)
async def _get_tag_subscriptions(cur_user: CurUserDep):
    return get_user_tag_subscriptions(cur_user)


@route("prompt", "create-tag-subscription", response_class=HTMLResponse)
async def _create_tag_subscription(dto: TagSubscriptionDTODep, cur_user: CurUserDep):
    try:
        async def get_tag():
            if len(dto.tags) == 1:
                return await to_thread(find_tag, dto.tags[0])
            return None
        tag, tag_subscription = await asyncio.gather(
            get_tag(), to_thread(create_tag_subscription, dto, cur_user)
        )
        return get_html_content("fragments/tag-subscription.html", {
            "cur_user": cur_user, "tag": tag, "tags": tag_subscription.tags,
            "tag_subscription": tag_subscription,
        })
    except SlugDuplicationError as exc:
        raise HTTPException(status_code=409, detail=exc.to_dict())


@route("delete", "delete-tag-subscription",
       response_class=HTMLResponse)
async def _delete_tag_subscription(tag_subscription_id: str, cur_user: CurUserDep):
    try:
        tag_subscription = delete_tag_subscription(tag_subscription_id, cur_user)
        return get_html_content("fragments/tag-subscription.html", {
            "cur_user": cur_user,
            "tag": find_tag(tag_subscription.tags[0]) if len(tag_subscription.tags) == 1 else None,
            "tags": tag_subscription.tags,
            "tag_subscription": None,
        })
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@route("patch", "update-tag", response_class=JSONResponse)
async def _update_tag(update_tag_dto: UpdateTagDTODep, tag: TagDep,
                              cur_user: CurUserDep,
                              request: Request) -> str:
    update_tag(tag, update_tag_dto, cur_user, request)
    return get_tag_url(request, tag)


@route("get", "get-tags", response_class=JSONResponse)
async def _get_tags(query_dto: TagQueryDep) -> list[Tag]:
    return get_tags(query_dto)


@route("get", "tags-fragment", response_class=HTMLResponse)
async def tags_fragment(query_dto: TagQueryDep) -> str:
    return get_html_content("fragments/tags.html", {
        "tags": get_tags(query_dto),
    })


@route("get", "users-fragment", response_class=HTMLResponse)
async def users_fragment(query_dto: UserQueryDep, cur_user: OptCurUserDep) -> str:
    return get_html_content("fragments/users.html", {
        "users": get_users(query_dto, cur_user),
        "cur_user": cur_user,
    })


@route("prompt", "update-user-status", response_class=JSONResponse)
async def _update_user_status(user: UserDep, update_user_status_dto: UpdateUserStatusDTODep,
                              cur_user: CurUserDep, request: Request) -> str:
    update_user_status(user, update_user_status_dto, cur_user, request)
    return get_user_url(request, user)


@route("prompt", "update-user-impression", response_class=HTMLResponse)
async def _update_user_impression(user: UserDep, update_user_impression_dto: UpdateUserImpressionDTODep,
                                  cur_user: CurUserDep, request: Request) -> str:
    update_user_impression(user, update_user_impression_dto, cur_user, request)
    (
        user,
        user_impression,
    ) = await asyncio.gather(
        to_thread(find_user, user.id),
        to_thread(find_user_impression, user, cur_user),
    )
    return get_html_content("fragments/user-impressions.html", {
        "user": user,
        "user_impression": user_impression,
        "cur_user": cur_user,
    })


@route("patch", "update-user-activity-settings", response_class=JSONResponse)
async def _update_user_activity_settings(dto: UpdateUserActivitySettingsDTODep, user: UserDep, cur_user: CurUserDep,
                                         request: Request) -> str:
    update_user_activity_settings(user, dto, cur_user)
    return get_user_url(request, user)


@route("patch", "update-user-interests-settings",
       response_class=JSONResponse)
async def _update_user_interests_settings(dto: UpdateUserInterestsSettingsDTODep, user: UserDep, cur_user: CurUserDep,
                                          request: Request) -> str:
    update_user_interests_settings(user, dto, cur_user)
    return get_user_url(request, user)


@route("patch", "update-user", response_class=JSONResponse)
async def _update_user(update_user_dto: UpdateUserDTODep, user: UserDep, cur_user: CurUserDep, request: Request) -> str:
    update_user(user, update_user_dto, cur_user, request)
    return get_user_url(request, user)


@route("get", "user-prompts-fragment", response_class=HTMLResponse)
async def user_prompts_fragment(user: UserDep, query_dto: PromptQueryDep, cur_user: OptCurUserDep) -> str:
    return get_html_content("fragments/prompts.html", {
        "query": query_dto,
        "prompts": get_latest_prompts_by_user(user, query_dto, cur_user),
        "cur_user": cur_user,
    })




@route("prompt", "generate-sitemap")
async def _generate_sitemap(cur_user: CurUserDep, request: Request) -> dict:
    from api_utils import generate_sitemap

    urls_count, sitemap_url = generate_sitemap(cur_user, request)
    return {"urls_count": urls_count, "sitemap_url": sitemap_url}


@route("prompt", "drop-cdn-cache")
async def _drop_cdn_cache(cur_user: CurUserDep) -> dict:
    from api_utils import drop_cdn_cache

    success, items_count = drop_cdn_cache(cur_user)
    return {"success": success, "items_count": items_count}
