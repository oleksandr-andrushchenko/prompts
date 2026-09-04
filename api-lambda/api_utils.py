from prompt_dtos import (
    PromptCommentDTO, PromptDTO, UpdatePromptCommentDTO, UpdatePromptDTO, UpdatePromptImpressionDTO,
    UpdatePromptStatusDTO, UpdateTagDTO,
)
from tag_subscription_dtos import TagSubscriptionDTO
from basic_dtos import ContactMessageDTO, FileDTO, ImageFileDTO
from shared_utils import *
from shared_utils import get_tags
from user_dtos import (
    UpdateUserDTO, UpdateUserImpressionDTO, UpdateUserStatusDTO,
    UpdateUserActivitySettingsDTO, UpdateUserInterestsSettingsDTO,
    UserImpressionAction,
)
from prompt_models import get_prompt_model


def drop_cdn_cache(user: User) -> tuple[bool, int]:
    verify_authorization(user, Permission.DROP_CDN_CACHE)
    res = _drop_cdn_cache()
    return res.get("success"), res.get("items_count")


def _drop_cdn_cache(*urls) -> dict[str, Any]:
    items = set()
    for u in urls:
        if isinstance(u, str):
            items.add(u)
        elif isinstance(u, (list, tuple, set)):
            items.update(u)
        else:
            raise TypeError(f"Unsupported type: {type(u)}")

    # Resolve paths
    if items:
        paths = []
        for p in items:
            if not isinstance(p, str):
                raise TypeError(f"Invalid path type: {type(p)} (expected str)")

            if not p.startswith("/"):
                raise ValueError(f"Invalid CloudFront path (must start with '/'): {p}")

            paths.append(p)

        if len(paths) > 3000:
            raise ValueError("CloudFront supports max 3000 paths per invalidation request")
    else:
        paths = ["/*"]

    if not is_prod():
        return {
            "success": True,
            "invalidation_id": "",
            "status": "InProgress",
            "items_count": len(paths),
        }

    client = _get_cf_client()
    distribution_id = get_cf_distribution_id()
    response = client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {
                "Quantity": len(paths),
                "Items": paths,
            },
            "CallerReference": str(uuid.uuid4()),
        },
    )

    metadata = response.get("ResponseMetadata", {})
    invalidation = response.get("Invalidation", {})

    return {
        "success": metadata.get("HTTPStatusCode") == 201,
        "invalidation_id": invalidation.get("Id"),
        "status": invalidation.get("Status"),
        "items_count": len(paths),
    }


def safe_execute(label: str, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"{label} failed: {e}")
        return None


def generate_sitemap(user: User, req) -> tuple[int, str]:
    verify_authorization(user, Permission.GENERATE_SITEMAP)

    today = datetime.utcnow().date().isoformat()

    def lastmod(ts_ms, fallback_ts_ms=None):
        ts_ms = ts_ms or fallback_ts_ms
        if not ts_ms:
            return today
        return datetime.fromtimestamp(
            float(ts_ms) / 1000,
            tz=timezone.utc
        ).date().isoformat()

    urls = []

    # Static
    def url(route: str) -> str:
        return get_url(req, route, True)

    urls.extend([
        (url("index"), today),
        (url("tags"), today),
        (url("contacts"), today),
        (url("rules"), today),
        (url("terms"), today),
        (url("earn"), today),
    ])

    # Prompt lists
    def prompts_url(tp: PromptQueryType, tg: Tag | None = None) -> str:
        return get_prompts_url(req, type=tp, tags=[tg.slug] if tg else [], absolute=True)

    for type_ in PromptQueryType:
        urls.append((prompts_url(type_), today))
        for tag in get_tags(TagQueryDTO(limit=1000)):
            if tag.prompts_count > 0:
                urls.append((prompts_url(type_, tag), today))

    # Prompts
    def prompt_url(prompt: Prompt) -> str:
        return get_prompt_url(req, prompt, absolute=True)

    offset = None
    while prompts := get_latest_prompts(PromptQueryDTO(status=PromptStatus.PUBLISHED, limit=1000, offset=offset)):
        urls.extend([(prompt_url(prompt), lastmod(prompt.updated_at, prompt.created_at)) for prompt in prompts])
        offset = prompts[-1].offset
        if not offset:
            break

    # User lists
    def users_url(tp: UserQueryType) -> str:
        return get_users_url(req, type=tp, absolute=True)

    for type_ in UserQueryType:
        urls.append((users_url(type_), today))

    # Users
    def user_url(user_: User) -> str:
        return get_user_url(req, user_, absolute=True)

    offset = None
    while users := get_latest_users(
            UserQueryDTO(status=UserStatus.ACTIVE, limit=1000, offset=offset)):
        urls.extend([(user_url(user), lastmod(user.updated_at, user.created_at)) for user in users])
        offset = users[-1].offset
        if not offset:
            break

    # Save
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{''.join([f"""<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>""" for (loc, lastmod) in urls])}</urlset>"""

    sitemap_filename = save_public_file(
        FileDTO(content=sitemap_xml.encode("utf-8"), filename="sitemap.xml"),
        filename="sitemap.xml",
    )
    sitemap_url = get_static_url(req, sitemap_filename, absolute=True)

    # Invalidate CDN cache
    if is_prod():
        safe_execute("CF invalidation", _drop_cdn_cache, ["/sitemap.xml"])

    # Notify engines
    if is_prod():
        import httpx
        with httpx.Client(timeout=5.0) as client:
            safe_execute("Google SM notify", client.get, "https://www.google.com/ping", params={"sitemap": sitemap_url})
            safe_execute("Bing SM notify", client.get, "https://www.bing.com/ping", params={"sitemap": sitemap_url})

    return len(urls), sitemap_url


def create_tag_subscription(dto: TagSubscriptionDTO, user: User) -> TagSubscription:
    tag_subscription_id, now, key = str(uuid.uuid4()), utc_now(), tag_subscription_key(dto.tags)
    transacts = []
    add_dynamodb_put_transact(transacts, (f"USER#{user.id}", f"TAG_SUBSCRIPTION#{tag_subscription_id}"),
                              {"tag_subscription_id": tag_subscription_id, "user_id": user.id,
                               "tags": dto.tags, "tag_subscription_key": key, "created_at": now})
    add_dynamodb_put_transact(transacts, (f"TAG_SUBSCRIBERS#{key}", f"USER#{user.id}"),
                              {"user_id": user.id, "tag_subscription_id": tag_subscription_id,
                               "tag_subscription_key": key, "created_at": now}, new_pk_only=True)
    add_dynamodb_user_update_transact(transacts, user, deltas={"tag_subscriptions_count": 1})
    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as exc:
        if exc.is_conditional():
            raise SlugDuplicationError("Tag subscription already exists", "tags")
        raise
    return TagSubscription(tag_subscription_id, user.id, dto.tags, now)


def delete_tag_subscription(tag_subscription_id: str, user: User) -> TagSubscription:
    item = get_dynamodb_item(f"USER#{user.id}", f"TAG_SUBSCRIPTION#{tag_subscription_id}")
    if not item:
        raise UserNotFoundError("Tag subscription not found")
    subscription = tag_subscription_from_dynamodb(item)
    key = item["tag_subscription_key"]
    transacts = []
    add_dynamodb_delete_transact(
        transacts, (f"USER#{user.id}", f"TAG_SUBSCRIPTION#{tag_subscription_id}")
    )
    add_dynamodb_delete_transact(
        transacts, (f"TAG_SUBSCRIBERS#{key}", f"USER#{user.id}")
    )
    add_dynamodb_user_update_transact(
        transacts, user, deltas={"tag_subscriptions_count": -1}
    )
    dynamodb_transact_write(transacts)
    return subscription


def update_tag(tag: Tag, update_tag_dto: UpdateTagDTO, cur_user: User,
                       req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_TAG, tag)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    changes = update_tag_dto.get_changes(tag)
    if not changes:
        return

    now = utc_now()

    new_name = changes.pop("name", None)
    if new_name is not None:
        new_name = new_name.strip()
        if new_name != tag.name:
            changes["name"] = new_name

    image_action = changes.pop("image_action", "keep")

    if image_action == "delete":
        changes["image_filename"] = None
    elif image_action == "keep":
        changes.pop("image_filename", None)

    if not changes:
        return

    old_image = tag.image_filename
    old_slug = tag.slug
    slug = to_kebab_case(changes["name"]) if "name" in changes else old_slug
    slug_changed = slug != old_slug
    transacts = []

    if slug_changed:
        old_item = get_dynamodb_item(f"TAG#{old_slug}", "META")
        if old_item is None:
            raise TagNotFoundError(f"Tag '{old_slug}' not found")

        new_item = {k: v for k, v in old_item.items() if k not in {"pk", "sk"}}
        new_item.update(changes)
        new_item["tag_name_sk"] = slug
        new_item["updated_at"] = now

        redirect_item = {
            "tag_name_sk": old_slug,
            "redirect_to": slug,
            "created_at": now,
        }
        add_dynamodb_put_transact(transacts, (f"TAG_REDIRECT#{old_slug}", "META"), redirect_item, new_pk_only=True)
        add_dynamodb_put_transact(transacts, (f"TAG#{slug}", "META"), new_item, new_pk_only=True)
        add_dynamodb_delete_transact(transacts, (f"TAG#{old_slug}", "META"))

        for prompt in get_latest_prompts_by_tags(PromptQueryDTO(tags=[old_slug], limit=1000)):
            old_tags = list(prompt.tags)
            tags = list(dict.fromkeys(slug if tag == old_slug else tag for tag in old_tags))

            add_delete_tag_combos_transact(transacts, prompt, old_slug)
            add_dynamodb_prompt_update_transact(transacts, prompt, {"tags": tags})
            add_put_tag_combos_transact(transacts, prompt, slug)
    else:
        add_dynamodb_tag_update_transact(transacts, tag, changes)

    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as e:
        if e.is_conditional():
            raise SlugDuplicationError(field="name")
        raise

    if "name" in changes:
        tag.name = changes["name"]
    if slug_changed:
        tag.slug = slug
    if "image_filename" in changes:
        tag.image_filename = changes["image_filename"]

    if old_image and image_action in {"delete", "replace"}:
        drop_public_file(old_image)


def save_public_file(file_dto: FileDTO, filename: str = None) -> str:
    if not filename:
        file_ext = file_dto.extension
        filename = str(uuid.uuid4())
        if isinstance(file_dto, ImageFileDTO):
            try:
                width, height = get_image_dimensions(file_dto.content)
                filename += f"_{width}x{height}"
            except ValueError:
                pass
        filename += f".{file_ext}"

    if not is_prod():
        filepath = os.path.join(get_static_files_dir(), filename)
        with open(filepath, "wb") as f:
            f.write(file_dto.content)
        return filename
    from io import BytesIO
    stream = BytesIO(file_dto.content)
    stream.seek(0)

    import mimetypes
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    get_s3_client().upload_fileobj(
        stream,
        get_static_s3_bucket(),
        filename,
        ExtraArgs={
            "ContentType": content_type,
            "ContentDisposition": "inline",
        },
    )
    return filename


def drop_public_file(filename: str) -> None:
    if not is_prod():
        # filepath = os.path.join(get_static_files_dir(), filename)
        # if os.path.exists(filepath):
        #     os.remove(filepath)
        return

    get_s3_client().delete_object(Bucket=get_static_s3_bucket(), Key=filename)


def create_prompt(prompt_dto: PromptDTO, cur_user: User) -> Prompt:
    verify_authorization(cur_user, Permission.CREATE_PROMPT)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    now = utc_now()
    status = PromptStatus.UNPUBLISHED
    prompt_id = str(uuid.uuid4())
    title = prompt_dto.title
    description = prompt_dto.description
    category = prompt_dto.category
    outputs = prompt_dto.outputs
    template = prompt_dto.template
    image_filenames = prompt_dto.image_filenames
    tags = sanitize_tags(prompt_dto.tags)
    slug = to_kebab_case(title)

    transacts = []

    prompt_item = {
        "id": prompt_id,
        "title": title,
        "description": description,
        "category": category,
        "outputs": outputs,
        "prompt_slug": slug,
        "user_id": cur_user.id,
        "user_name": cur_user.name,
        "template": template,
        "image_filenames": image_filenames,
        "tags": tags,
        "rating_sk": compute_rating_sk(0, now),
        "status": status,
        "created_at": now,
        "prompt_status_pk": f"PROMPT#{status}",
        "prompt_user_status_pk": f"PROMPT#{cur_user.id}#{status}",
    }
    models = [get_prompt_model(model_slug) for model_slug in prompt_dto.models]
    prompt_item["models"] = [
        {"title": model.title, "slug": model.slug, "version": model.version}
        for model in models if model
    ]
    if cur_user.username:
        prompt_item["user_slug"] = cur_user.username
    add_dynamodb_put_transact(transacts, (f"PROMPT#{prompt_id}", "META"), prompt_item, new_pk_only=True)

    add_user_activity_transact(transacts, cur_user, "prompt.created", "prompt", prompt_id, title,
                               f"/prompts/{prompt_id}", cur_user.id, now)
    add_dynamodb_user_update_transact(transacts, cur_user, deltas={
        "unpublished_prompts_count": 1,
    })
    # todo: should be unique in combination with username (cur_user, prompt)
    add_dynamodb_put_transact(transacts, (f"PROMPT_SLUG#{slug}", "META"), {"prompt_id": prompt_id}, new_pk_only=True)

    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as e:
        if e.is_conditional():
            raise SlugDuplicationError(field="title")
        raise

    return prompt_from_dynamodb(prompt_item)


def update_prompt(prompt: Prompt, update_prompt_dto: UpdatePromptDTO, cur_user: User, req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_PROMPT, prompt)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    changes = update_prompt_dto.get_changes(prompt)
    if not changes:
        return

    if "models" in changes:
        changes["models"] = [
            {"title": model.title, "slug": model.slug, "version": model.version}
            for model_slug in changes["models"]
            if (model := get_prompt_model(model_slug))
        ]

    if "tags" in changes:
        changes["tags"] = sanitize_tags(changes["tags"])
    old_status = prompt.status
    published_already = old_status == PromptStatus.PUBLISHED
    now = utc_now()

    transacts = []

    old_title = prompt.title
    if "title" in changes:
        new_title = changes["title"]
        if published_already and get_text_diff_percentage(old_title, new_title) > 10:
            changes["status"] = PromptStatus.UNPUBLISHED
        old_slug = prompt.slug
        slug = to_kebab_case(new_title)
        if old_slug != slug:
            changes["prompt_slug"] = slug
            # Create redirect item so old slug resolves
            redirect_item = {
                "prompt_slug": old_slug,
                "redirect_to": slug,
                "created_at": now
            }
            add_dynamodb_put_transact(transacts, (f"PROMPT_REDIRECT#{old_slug}", "META"), redirect_item, new_pk_only=True)
            # Create new slug lock
            add_dynamodb_put_transact(transacts, (f"PROMPT_SLUG#{slug}", "META"), {"prompt_id": prompt.id},
                                      new_pk_only=True)

    old_tags = list(prompt.tags)
    tags_changed = False
    if "tags" in changes:
        changes["tags"] = sanitize_tags(changes["tags"])
        tags_changed = sorted(changes["tags"]) != sorted(old_tags)
        if published_already and tags_changed:
            changes["status"] = PromptStatus.UNPUBLISHED

    if published_already and changes.get("status") == PromptStatus.UNPUBLISHED:
        add_decrease_tags_rating_transact(transacts, old_tags, now)
        add_delete_tag_combos_transact(transacts, prompt)
    elif tags_changed:
        add_delete_tag_combos_transact(transacts, prompt)

    prompt_owner = get_user(prompt.owner_id)
    if prompt.user_name != prompt_owner.name:
        changes["user_name"] = prompt_owner.name
    if prompt.user_slug != prompt_owner.username:
        changes["user_slug"] = prompt_owner.username

    prompt_owner_deltas = {}

    status = changes.get("status", prompt.status)
    status_changed = status != old_status
    if status_changed:
        # Update prompt lists
        changes["prompt_status_pk"] = f"PROMPT#{status}"
        changes["prompt_user_status_pk"] = f"PROMPT#{prompt.user_id}#{status}"

        # User prompt counters
        prompt_owner_deltas[f"{old_status}_prompts_count"] = -1
        prompt_owner_deltas[f"{status}_prompts_count"] = 1

    add_dynamodb_user_update_transact(transacts, prompt_owner, deltas=prompt_owner_deltas)
    add_dynamodb_prompt_update_transact(transacts, prompt, changes)

    if cur_user.id != prompt_owner.id:
        add_dynamodb_user_update_transact(transacts, cur_user)

    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as e:
        if e.is_conditional():
            raise SlugDuplicationError(field="title")
        raise

    for k, v in changes.items():
        if k == "prompt_slug":
            k = "slug"
        if k != "models" and hasattr(prompt, k):
            setattr(prompt, k, v)
    if "models" in changes:
        prompt.models = [
            model for model_data_item in changes["models"]
            if (model := get_prompt_model(model_data_item["slug"], model_data_item["version"]))
        ]


def create_prompt_comment(prompt: Prompt, prompt_comment_dto: PromptCommentDTO, cur_user: User,
                           req) -> PromptComment:
    verify_authorization(cur_user, Permission.CREATE_PROMPT_COMMENT)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    now = utc_now()
    comment_id = f"{now}#{str(uuid.uuid4())}"

    transacts = []

    prompt_comment_item = {
        "id": comment_id,

        "user_id": cur_user.id,
        "user_name": cur_user.name,
        "user_image_filename": cur_user.image_filename,
        "user_username": cur_user.username,

        "prompt_id": prompt.id,
        "prompt_title": prompt.title,
        "comment_prompt_slug": prompt.slug,
        "prompt_comment_pk": "PROMPT_COMMENT",
        "prompt_comment_user_pk": f"USER#{cur_user.id}",

        "text": prompt_comment_dto.text,
        "created_at": now,
    }

    add_dynamodb_put_transact(transacts, (f"PROMPT#{prompt.id}", f"COMMENT#{comment_id}"), prompt_comment_item)
    add_dynamodb_prompt_update_transact(transacts, prompt, deltas={"comments_count": 1})
    add_user_activity_transact(transacts, cur_user, "comment.created", "comment", comment_id, prompt.title,
                               f"/prompts/{prompt.id}#comment-{comment_id}", cur_user.id, now)
    add_dynamodb_user_update_transact(transacts, cur_user, deltas={
        "prompt_comments_count": 1,
    })

    if cur_user.id != prompt.owner_id:
        prompt_owner = get_user(prompt.owner_id)
        add_dynamodb_user_update_transact(transacts, prompt_owner)

    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as e:
        if e.is_conditional():
            raise SlugDuplicationError(field="title")
        raise

    return prompt_comment_from_dynamodb(prompt_comment_item)


def update_prompt_comment(prompt: Prompt, prompt_comment: PromptComment,
                           update_prompt_comment_dto: UpdatePromptCommentDTO,
                           cur_user: User, req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_PROMPT_COMMENT, prompt_comment)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    if prompt_comment.likes_count != 0 or prompt_comment.dislikes_count != 0:
        raise PromptCommentNonEditableError()

    changes = update_prompt_comment_dto.get_changes(prompt_comment)
    if not changes:
        return

    transacts = []

    add_dynamodb_update_transact(transacts, (f"PROMPT#{prompt.id}", f"COMMENT#{prompt_comment.id}"), changes)

    add_dynamodb_user_update_transact(transacts, cur_user)

    if cur_user.id != prompt.owner_id:
        prompt_owner = get_user(prompt.owner_id)
        add_dynamodb_user_update_transact(transacts, prompt_owner)

    dynamodb_transact_write(transacts)

    for k, v in changes.items():
        if hasattr(prompt_comment, k):
            setattr(prompt_comment, k, v)


def update_dynamodb_item(
        key: tuple[str, str],
        changes: dict[str, Any] | None = None,
        deltas: dict[str, Any] | None = None,
        add_updated_at: bool = True
) -> None:
    param_dict = dict(locals())
    update_item_params = build_dynamodb_update_item_params(**param_dict)
    get_dynamodb_table().update_item(**update_item_params["Update"])


def update_user(user: User, update_user_dto: UpdateUserDTO, cur_user: User, req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_USER, user)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    changes = update_user_dto.get_changes(user)
    if not changes:
        return

    now = utc_now()

    if "website" in changes and changes["website"]:
        website = str(changes["website"]).rstrip("/")
        if website == user.website:
            changes.pop("website")
        else:
            changes["website"] = website

    transacts = []
    avatar_action = changes.pop("avatar_action", "keep")

    if avatar_action == "delete":
        changes["image_filename"] = None
    elif avatar_action == "keep":
        changes.pop("image_filename", None)

    if not changes:
        return

    old_avatar = user.image_filename
    prompt_user_changes = {}
    comment_user_changes = {}

    if "name" in changes:
        prompt_user_changes["user_name"] = changes["name"]
        comment_user_changes["user_name"] = changes["name"]

    if "username" in changes:
        old_slug = user.username
        slug = changes["username"]

        if old_slug and slug:
            redirect_item = {
                "username": old_slug,
                "redirect_to": slug,
                "created_at": now
            }
            add_dynamodb_put_transact(transacts, (f"USER_REDIRECT#{old_slug}", "META"), redirect_item, new_pk_only=True)

        if slug:
            add_dynamodb_put_transact(transacts, (f"USER_SLUG#{slug}", "META"), {"user_id": user.id}, new_pk_only=True)
        elif old_slug:
            add_dynamodb_delete_transact(transacts, (f"USER_SLUG#{old_slug}", "META"))

        prompt_user_changes["user_slug"] = slug
        comment_user_changes["user_username"] = slug

    if "image_filename" in changes:
        comment_user_changes["user_image_filename"] = changes["image_filename"]

    if prompt_user_changes:
        for prompt in get_all_prompts_by_user(user):
            add_dynamodb_prompt_update_transact(transacts, prompt, prompt_user_changes)

    if comment_user_changes:
        for comment in get_all_prompt_comments_by_user(user):
            add_dynamodb_update_transact(
                transacts,
                (f"PROMPT#{comment.prompt_id}", f"COMMENT#{comment.id}"),
                comment_user_changes,
            )

    add_dynamodb_user_update_transact(transacts, user, changes, {})

    if user.id != cur_user.id:
        add_dynamodb_user_update_transact(transacts, cur_user)

    try:
        dynamodb_transact_write(transacts)
    except DynamoDBTransactionError as e:
        if e.is_conditional():
            raise SlugDuplicationError(field="username")
        raise

    if old_avatar and avatar_action in {"delete", "replace"}:
        drop_public_file(old_avatar)


def update_user_activity_settings(user: User, dto: UpdateUserActivitySettingsDTO, cur_user: User) -> None:
    verify_authorization(cur_user, Permission.UPDATE_USER, user)
    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()
    changes = dto.get_changes(user)
    if not changes:
        return
    update_dynamodb_item((f"USER#{user.id}", "META"), changes=changes)
    for k, v in changes.items():
        setattr(user, k, v)


def update_user_interests_settings(user: User, dto: UpdateUserInterestsSettingsDTO, cur_user: User) -> None:
    verify_authorization(cur_user, Permission.UPDATE_USER, user)
    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()
    changes = dto.get_changes(user)
    if not changes:
        return
    update_dynamodb_item((f"USER#{user.id}", "META"), changes=changes)
    user.show_interests = changes["show_interests"]


def update_user_status(user: User, update_user_status_dto: UpdateUserStatusDTO, cur_user: User, req) -> None:
    # logger.debug(f"update_user_status: user: {user}, cur_user: {cur_user}")
    verify_authorization(cur_user, Permission.UPDATE_USER_STATUS)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    changes = update_user_status_dto.get_changes()
    if not changes:
        return
    if not "comment" in changes:
        changes["comment"] = None

    status = changes["status"]
    changes["user_status_pk"] = f"USER#{status}"

    transacts = []

    add_dynamodb_user_update_transact(transacts, cur_user)

    if cur_user.id != user.id:
        add_dynamodb_user_update_transact(transacts, user, changes, {})

    # logger.debug(transacts)

    dynamodb_transact_write(transacts)


def update_prompt_status(prompt: Prompt, update_prompt_status_dto: UpdatePromptStatusDTO, cur_user: User,
                          req) -> None:
    # logger.debug(f"update_prompt_status: prompt: {prompt}, cur_user: {cur_user}")
    verify_authorization(cur_user, Permission.UPDATE_PROMPT_STATUS)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    if prompt.status == PromptStatus.PUBLISHED:
        raise PromptAlreadyPublishedError()

    changes = update_prompt_status_dto.get_changes()
    if not changes:
        return
    if not "comment" in changes:
        changes["comment"] = None

    old_status = prompt.status
    status = changes["status"]
    now = utc_now()

    transacts = []

    prompt_owner = get_user(prompt.owner_id)
    add_dynamodb_user_update_transact(transacts, prompt_owner, deltas={
        # User prompt counters
        f"{old_status}_prompts_count": -1,
        f"{status}_prompts_count": 1,
    })

    crossed_published_boundary = (old_status == PromptStatus.PUBLISHED) != (status == PromptStatus.PUBLISHED)
    if crossed_published_boundary and status == PromptStatus.PUBLISHED:
        if not prompt.published_at:
            changes["published_at"] = now
        if prompt_owner:
            changes["user_slug"] = prompt_owner.username

        add_increase_tags_rating_transact(transacts, prompt.tags, now)
        add_put_tag_combos_transact(transacts, prompt)
    elif crossed_published_boundary:
        add_decrease_tags_rating_transact(transacts, prompt.tags, now)
        add_delete_tag_combos_transact(transacts, prompt)

    changes["prompt_status_pk"] = f"PROMPT#{status}"
    changes["prompt_user_status_pk"] = f"PROMPT#{prompt.user_id}#{status}"

    add_dynamodb_prompt_update_transact(transacts, prompt, changes)

    if cur_user.id != prompt_owner.id:
        add_dynamodb_user_update_transact(transacts, cur_user)

    # logger.debug(transacts)

    dynamodb_transact_write(transacts)

    if status == PromptStatus.PUBLISHED:
        try:
            dispatch_prompt_published_event(prompt)
        except Exception:
            logger.exception("Unable to dispatch prompt published event")


def create_contact_message(message_dto: ContactMessageDTO, user: User = None) -> ContactMessage:
    user and verify_authorization(user, Permission.CREATE_CONTACT_MESSAGE)

    now = utc_now()
    message_id = str(uuid.uuid4())

    name = message_dto.name
    message = message_dto.message

    if is_prod():
        text = (
            f"New contact form submission:\n"
            f"ID: {message_id}\n"
            f"Name: {name}\n"
            f"Email: {message_dto.email}\n"
            f"Message: {message}\n"
            f"User ID: {user.id if user else 'N/A'}"
        )
        get_sns_client().publish(
            TopicArn=get_contact_topic_arn(),
            Message=text,
            Subject="New Contact Form Submission"
        )

    message_item = {
        "pk": f"CONTACT_MESSAGE#{message_id}",
        "sk": "META",
        "message_id": message_id,
        "name": name,
        "email": message_dto.email,
        "message": message,
        "created_at": now,
    }
    if user:
        message_item["user_id"] = user.id

    get_dynamodb_table().put_item(Item=message_item)

    return ContactMessage(
        id=message_id,
        name=message_item["name"],
        email=str(message_item["email"]),
        message=message_item["message"],
        user_id=message_item.get("user_id"),
        created_at=now,
    )


def update_prompt_impression(prompt: Prompt, update_prompt_impression_dto: UpdatePromptImpressionDTO,
                              cur_user: User,
                              req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_PROMPT_IMPRESSION, prompt)

    if cur_user.status == UserStatus.BANNED:
        raise UserBannedError()

    current_impression = find_prompt_impression(prompt, cur_user)
    current_action = current_impression.action if current_impression else None
    action = update_prompt_impression_dto.action
    prompt_impression_item = {
        "prompt_id": prompt.id,
        "user_id": cur_user.id,
        "action": action,
    }
    transacts = []

    prompt_deltas = {}
    prompt_imp_key = (f"PROMPT#{prompt.id}", f"IMP#{cur_user.id}")

    if action == PromptImpressionAction.LIKE:
        if current_action == PromptImpressionAction.LIKE:
            add_dynamodb_delete_transact(transacts, prompt_imp_key)
            prompt_deltas["likes_count"] = -1
            prompt_deltas["rating_sk"] = compute_rating_sk(-1)
        elif current_action == PromptImpressionAction.DISLIKE:
            add_dynamodb_update_transact(transacts, prompt_imp_key, {"action": PromptImpressionAction.LIKE})
            prompt_deltas["dislikes_count"] = -1
            prompt_deltas["likes_count"] = 1
            prompt_deltas["rating_sk"] = compute_rating_sk(2)
        else:
            add_dynamodb_put_transact(transacts, prompt_imp_key,
                                      {**prompt_impression_item, "action": PromptImpressionAction.LIKE},
                                      new_pk_only=True)
            prompt_deltas["likes_count"] = 1
            prompt_deltas["rating_sk"] = compute_rating_sk(1)

    elif action == PromptImpressionAction.DISLIKE:
        if current_action == PromptImpressionAction.DISLIKE:
            add_dynamodb_delete_transact(transacts, prompt_imp_key)
            prompt_deltas["dislikes_count"] = -1
            prompt_deltas["rating_sk"] = compute_rating_sk(1)
        elif current_action == PromptImpressionAction.LIKE:
            add_dynamodb_update_transact(transacts, prompt_imp_key, {"action": PromptImpressionAction.DISLIKE})
            prompt_deltas["likes_count"] = -1
            prompt_deltas["dislikes_count"] = 1
            prompt_deltas["rating_sk"] = compute_rating_sk(-2)
        else:
            add_dynamodb_put_transact(transacts, prompt_imp_key,
                                      {**prompt_impression_item, "action": PromptImpressionAction.DISLIKE},
                                      new_pk_only=True)
            prompt_deltas["dislikes_count"] = 1
            prompt_deltas["rating_sk"] = compute_rating_sk(-1)

    add_dynamodb_prompt_update_transact(transacts, prompt, deltas=prompt_deltas)

    add_dynamodb_user_update_transact(transacts, cur_user)

    if cur_user.id != prompt.owner_id:
        prompt_owner = get_user(prompt.owner_id)
        add_dynamodb_user_update_transact(transacts, prompt_owner)

    logger.debug(transacts)
    dynamodb_transact_write(transacts)


def update_user_impression(user: User, update_relation_dto: UpdateUserImpressionDTO, cur_user: User, req) -> None:
    verify_authorization(cur_user, Permission.UPDATE_USER_IMPRESSION, user)

    if user.status == UserStatus.BANNED:
        raise UserBannedError()

    if user.id == cur_user.id:
        return

    current_relation = find_user_impression(user, cur_user)
    current_action = current_relation.action if current_relation else None
    action = update_relation_dto.action
    relation_item = {
        "user_id": cur_user.id,
        "target_user_id": user.id,
        "action": action,
    }
    transacts = []

    cur_user_deltas = {
    }
    user_deltas = {
    }
    relation_key = (f"USER#{cur_user.id}", f"REL#{user.id}")

    if action == UserImpressionAction.FOLLOW:
        if current_action == UserImpressionAction.FOLLOW:
            # Unfollow
            add_dynamodb_delete_transact(transacts, relation_key)
            cur_user_deltas["following_count"] = -1
            user_deltas["followers_count"] = -1
            user_deltas["rating_sk"] = compute_rating_sk(-1)
        elif current_action == UserImpressionAction.BLOCK:
            # Switching from block to follow
            add_dynamodb_update_transact(transacts, relation_key, {"action": UserImpressionAction.FOLLOW})
            cur_user_deltas["following_count"] = 1
            user_deltas["followers_count"] = 1
            user_deltas["rating_sk"] = compute_rating_sk(2)
        else:
            # New follow
            add_dynamodb_put_transact(transacts, relation_key, relation_item, new_pk_only=True)
            cur_user_deltas["following_count"] = 1
            user_deltas["followers_count"] = 1
            user_deltas["rating_sk"] = compute_rating_sk(1)

    elif action == UserImpressionAction.BLOCK:
        if current_action == UserImpressionAction.BLOCK:
            # Unblock
            add_dynamodb_delete_transact(transacts, relation_key)
            user_deltas["rating_sk"] = compute_rating_sk(1)
        elif current_action == UserImpressionAction.FOLLOW:
            # Switching from follow to block
            add_dynamodb_update_transact(transacts, relation_key, {"action": UserImpressionAction.BLOCK})
            cur_user_deltas["following_count"] = -1
            user_deltas["followers_count"] = -1
            user_deltas["rating_sk"] = compute_rating_sk(-2)
        else:
            # New block
            add_dynamodb_put_transact(transacts, relation_key, relation_item, new_pk_only=True)
            user_deltas["rating_sk"] = compute_rating_sk(-1)

    add_dynamodb_user_update_transact(transacts, cur_user, deltas=cur_user_deltas)
    add_dynamodb_user_update_transact(transacts, user, deltas=user_deltas)

    dynamodb_transact_write(transacts)


def get_email_files_dir() -> str:
    return config.get("email_files_dir")


def get_static_s3_bucket() -> str:
    return config.get("static_s3_bucket")


def get_contact_topic_arn():
    return get_config().get("contact_topic_arn")


def get_ses_from_email():
    return get_config().get("ses_from_email")


def dispatch_prompt_published_event(prompt: Prompt) -> None:
    handle_prompt_published_event(PromptPublishedEvent(prompt))


def save_email_to_disk(sender: str, recipient: str, subject: str, text_body: str, html_body: str) -> None:
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    emails_dir = get_email_files_dir()
    os.makedirs(emails_dir, exist_ok=True)
    email_path = os.path.join(emails_dir, f"{utc_now()}-{uuid.uuid4()}.eml")
    with open(email_path, "wb") as email_file:
        email_file.write(message.as_bytes())
    logger.info("Saved development email to %s", email_path)


def handle_prompt_published_event(event: PromptPublishedEvent) -> None:
    from itertools import combinations

    prompt = event.prompt
    matching_subscription_tags = {}

    for size in range(1, len(prompt.tags) + 1):
        for combo in combinations(sorted(prompt.tags), size):
            subscription_key = "TAG_SUBSCRIBERS#" + "#".join(combo)
            exclusive_start_key = None
            while True:
                response = query_dynamodb_table(
                    key_condition_expr=Key("pk").eq(subscription_key),
                    exclusive_start_key=exclusive_start_key,
                )
                for item in response.get("Items", []):
                    matching_subscription_tags.setdefault(item["user_id"], set()).add(combo)
                exclusive_start_key = response.get("LastEvaluatedKey")
                if not exclusive_start_key:
                    break

    if not matching_subscription_tags:
        return

    sender = get_ses_from_email()
    if is_prod() and not sender:
        logger.warning("Prompt publication notification skipped: SES_FROM_EMAIL is not configured")
        return
    sender = sender or "no-reply@localhost"

    base_url = get_web_base_url().rstrip('/')
    prompt_url = f"{base_url}/prompts/{prompt.id}"
    subject = f"New prompt matching your interests: {prompt.title}"

    for user_id, subscriptions in matching_subscription_tags.items():

        if user_id == prompt.user_id:
            continue
        user = find_user(user_id)
        if not user or not user.email:
            continue

        tag_links = [
            {
                "name": " + ".join(subscription_tags),
                "url": f"{base_url}/prompts?{urlencode([('type', 'latest'), ('status', 'published')] + [('tags', tag) for tag in subscription_tags])}",
            }
            for subscription_tags in sorted(subscriptions)
        ]
        subscribed_tags_text = ", ".join(link["name"] for link in tag_links)
        text_body = (
                f"Hello {user.name or 'there'},\n\n"
                "A new prompt matching your interests was published:\n\n"
                f"{prompt.title}\n"
                f"Subscribed interests: {subscribed_tags_text}\n"
                + "\n".join(f"{tag['name']}: {tag['url']}" for tag in tag_links)
                + f"\n\nRead it here: {prompt_url}\n\n"
                  f"Best regards,\n{get_config().get('site_name', 'The team')}\n"
        )
        html_body = get_html_content("emails/prompt-published-notification.html", {
            "recipient_name": user.name or "there",
            "prompt_title": prompt.title,
            "prompt_url": prompt_url,
            "tag_links": tag_links,
        })
        try:
            if not is_prod():
                save_email_to_disk(sender, user.email, subject, text_body, html_body)
                continue
            get_ses_client().send_email(
                Source=sender,
                Destination={"ToAddresses": [user.email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                },
            )
        except Exception:
            logger.exception(
                "Unable to send prompt publication notification",
                extra={"user_id": user_id, "prompt_id": prompt.id},
            )


def get_cf_distribution_id() -> str:
    return get_config().get("cf_distribution_id")


@lru_cache
def get_s3_client():
    import boto3
    return boto3.client("s3")


@lru_cache
def _get_cf_client():
    import boto3
    return boto3.client("cloudfront")


@lru_cache
def get_sns_client():
    import boto3
    return boto3.client("sns")


@lru_cache
def get_ses_client():
    import boto3
    return boto3.client("ses", region_name=get_aws_region())


def get_image_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) for JPEG, PNG, GIF images from raw bytes."""

    import struct

    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 24:
            raise ValueError("PNG file too short")
        width, height = struct.unpack(">II", data[16:24])
        return width, height

    # GIF
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        if len(data) < 10:
            raise ValueError("GIF file too short")
        width, height = struct.unpack("<HH", data[6:10])
        return width, height

    # JPEG
    elif data[:2] == b"\xff\xd8":
        offset = 2
        while offset + 1 < len(data):
            if data[offset] != 0xFF:
                raise ValueError("Invalid JPEG marker")
            marker = data[offset + 1]

            if 0xC0 <= marker <= 0xC3:
                # need at least 5 bytes for >xHH
                segment = data[offset + 5:offset + 10]
                if len(segment) < 5:
                    raise ValueError("JPEG SOF segment too short")
                _, height, width = struct.unpack(">xHH", segment)
                return width, height
            else:
                if offset + 4 > len(data):
                    raise ValueError("Truncated JPEG")
                seg_len = struct.unpack(">H", data[offset + 2:offset + 4])[0]
                if seg_len < 2:
                    raise ValueError("Invalid segment length")
                offset += 2 + seg_len

        raise ValueError("No SOF marker found in JPEG")

    raise ValueError("Unsupported image type")


def get_all_prompts_by_user(user: User) -> list[Prompt]:
    prompts = []
    for status in PromptStatus:
        exclusive_start_key = None
        while True:
            response = query_dynamodb_table(
                index_name="PROMPTS_BY_USER_STATUS_CREATED_AT_2",
                key_condition_expr=Key("prompt_user_status_pk").eq(f"PROMPT#{user.id}#{status}"),
                scan_index_forward=False,
                exclusive_start_key=exclusive_start_key,
            )
            prompts.extend(prompt_from_dynamodb(item) for item in response.get("Items", []))
            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                break
    return prompts


def get_all_prompt_comments_by_user(user: User) -> list[PromptComment]:
    comments = []
    exclusive_start_key = None
    while True:
        response = query_dynamodb_table(
            index_name="PROMPT_COMMENTS_BY_USER_CREATED_AT",
            key_condition_expr=Key("prompt_comment_user_pk").eq(f"USER#{user.id}"),
            scan_index_forward=False,
            exclusive_start_key=exclusive_start_key,
        )
        comments.extend(prompt_comment_from_dynamodb(item) for item in response.get("Items", []))
        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break
    return comments
