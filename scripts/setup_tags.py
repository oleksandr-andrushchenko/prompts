"""Set canonical tag names and fill missing tag images from Pexels.

The command is read-only unless ``--apply`` is provided and targets local
DynamoDB unless ``--production`` is provided. Set ``PEXELS_API_KEY`` in the
selected environment file before running it.

Examples (run from the repository root):

    # Local dry run, limited to ten tags.
    docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
      python scripts/setup_tags.py --limit 10

    # Apply the reviewed local changes.
    docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
      python scripts/setup_tags.py --limit 10 --apply

    # Production dry run. Add --apply only after reviewing its output.
    HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
    docker compose -f docker-compose.scripts.production.yml run --rm scripts-production \
      python scripts/setup_tags.py --production --limit 10

Existing tag images are preserved. Names are always derived from the current
slug (for example, ``marketing`` becomes ``Marketing`` and ``code-review``
becomes ``Code Review``).
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
DEFAULT_PEXELS_DELAY_SECONDS = 18.5
IMAGE_ORIENTATIONS = ("landscape", "portrait", "square")
AWS_CONFIG = Config(
    connect_timeout=5,
    read_timeout=60,
    retries={"max_attempts": 3, "mode": "standard"},
)
ENV_KEYS = {
    "APP_ENV",
    "APP_STAGE",
    "AWS_DEFAULT_REGION",
    "AWS_PROFILE",
    "AWS_PROJECT",
    "AWS_REGION",
    "AWS_STACK",
    "DYNAMODB_ENDPOINT",
    "DYNAMODB_PORT",
    "DYNAMODB_TABLE",
    "PEXELS_API_KEY",
    "STATIC_FILES_DIR",
    "STATIC_S3_BUCKET",
    "TAG_SETUP_USER_ID",
}
TAG_NAME_TOKENS = {
    "ai": "AI",
    "api": "API",
    "aws": "AWS",
    "cdn": "CDN",
    "chatgpt": "ChatGPT",
    "crm": "CRM",
    "css": "CSS",
    "gpt": "GPT",
    "hr": "HR",
    "html": "HTML",
    "http": "HTTP",
    "https": "HTTPS",
    "ios": "iOS",
    "iot": "IoT",
    "ip": "IP",
    "javascript": "JavaScript",
    "js": "JS",
    "json": "JSON",
    "llm": "LLM",
    "macos": "macOS",
    "mcp": "MCP",
    "openai": "OpenAI",
    "os": "OS",
    "pdf": "PDF",
    "php": "PHP",
    "qa": "QA",
    "rest": "REST",
    "rss": "RSS",
    "saas": "SaaS",
    "sdk": "SDK",
    "seo": "SEO",
    "sms": "SMS",
    "sql": "SQL",
    "svg": "SVG",
    "tts": "TTS",
    "typescript": "TypeScript",
    "ui": "UI",
    "url": "URL",
    "ux": "UX",
    "webp": "WebP",
    "xml": "XML",
    "yaml": "YAML",
}
TAG_IMAGE_SEARCH_QUERIES = {
    "api": "software API development",
    "chatgpt": "artificial intelligence chatbot",
    "code-review": "software code review",
    "crm": "customer relationship management business",
    "harness": "software testing automation",
    "html": "web development code",
    "llm": "artificial intelligence language model",
    "mcp": "artificial intelligence software development",
    "seo": "search engine optimization marketing",
    "ui": "user interface design",
    "ux": "user experience design",
}


@dataclass(frozen=True)
class PexelsPhoto:
    id: int
    image_url: str
    page_url: str
    photographer: str
    photographer_url: str
    alt: str
    orientation: str = "landscape"
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "image_url": self.image_url,
            "page_url": self.page_url,
            "photographer": self.photographer,
            "photographer_url": self.photographer_url,
            "alt": self.alt,
            "orientation": self.orientation,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset,
        }


@dataclass(frozen=True)
class TagPlan:
    slug: str
    current_name: str | None
    name: str
    current_image_filename: str | None
    photo: PexelsPhoto | None
    image_search_query: str | None = None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "current_name": self.current_name,
            "name": self.name,
            "current_image_filename": self.current_image_filename,
            "image_action": "keep" if self.current_image_filename else "add",
            "image_search_query": self.image_search_query,
            "pexels_photo": self.photo.to_dict() if self.photo else None,
        }


@dataclass(frozen=True)
class ImageFile:
    content: bytes
    source_filename: str


def positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return result


def nonnegative_float(value: str) -> float:
    result = float(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return result


def wait_for_pexels_request(last_request_at: float | None, delay: float) -> float:
    if last_request_at is not None:
        remaining_delay = delay - (time.monotonic() - last_request_at)
        if remaining_delay > 0:
            time.sleep(remaining_delay)
    return time.monotonic()


def slug_to_name(slug: str) -> str:
    return " ".join(
        TAG_NAME_TOKENS.get(token, token.capitalize())
        for token in slug.split("-")
    )


def image_search_query(slug: str) -> str:
    return TAG_IMAGE_SEARCH_QUERIES.get(slug, slug_to_name(slug))


def image_orientation(slug: str) -> str:
    bucket = int.from_bytes(hashlib.sha256(slug.encode()).digest()[:8], "big") % 3
    return IMAGE_ORIENTATIONS[bucket]


def square_image_url(original_url: str) -> str:
    parsed = urlparse(original_url)
    query = dict(parse_qsl(parsed.query))
    query.update({
        "auto": "compress",
        "cs": "tinysrgb",
        "fit": "crop",
        "h": "1200",
        "w": "1200",
    })
    return urlunparse(parsed._replace(query=urlencode(query)))


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def stack_outputs(stack_name: str) -> dict:
    response = boto3.client("cloudformation", config=AWS_CONFIG).describe_stacks(
        StackName=stack_name
    )
    return {
        item["OutputKey"]: item["OutputValue"]
        for item in response["Stacks"][0].get("Outputs", [])
    }


def _configure_production(args) -> dict:
    if os.getenv("APP_STAGE") != "prod":
        raise ValueError("--production requires APP_STAGE=prod")

    profile = os.getenv("AWS_PROJECT") or os.getenv("AWS_PROFILE")
    if profile:
        os.environ["AWS_PROFILE"] = profile
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if region:
        os.environ["AWS_REGION"] = region
        os.environ["AWS_DEFAULT_REGION"] = region
    if os.getenv("AWS_ACCESS_KEY_ID") == "dummy":
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_SESSION_TOKEN", None)
    os.environ.pop("DYNAMODB_ENDPOINT", None)

    stack = args.stack or os.getenv("AWS_STACK")
    if not stack:
        raise ValueError("production mode requires --stack or AWS_STACK")
    outputs = stack_outputs(stack)
    table_name = args.table or outputs.get("DynamoDbTableName") or os.getenv("DYNAMODB_TABLE")
    bucket = args.media_bucket or outputs.get("SiteBucketName") or os.getenv("STATIC_S3_BUCKET")
    if not table_name:
        raise ValueError("unable to resolve the production DynamoDB table")
    if args.apply and not bucket:
        raise ValueError("unable to resolve the production media bucket")
    if bucket:
        os.environ["STATIC_S3_BUCKET"] = bucket
    os.environ["DYNAMODB_TABLE"] = table_name

    identity = boto3.client("sts", config=AWS_CONFIG).get_caller_identity()
    target = {
        "stage": "prod",
        "environment": os.getenv("APP_ENV"),
        "stack": stack,
        "region": region,
        "aws_account": identity.get("Account"),
        "aws_principal": identity.get("Arn"),
        "table": table_name,
        "media_bucket": bucket,
        "mode": "apply" if args.apply else "dry-run",
    }
    return target


def _validate_local_endpoint(endpoint: str) -> None:
    hostname = urlparse(endpoint).hostname
    if hostname not in {"localhost", "127.0.0.1", "dynamodb"}:
        raise ValueError(f"local mode refuses non-local DynamoDB endpoint: {endpoint}")


def _configure_local(args) -> dict:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2"
    endpoint = (
        args.endpoint
        or os.getenv("DYNAMODB_ENDPOINT")
        or f"http://localhost:{os.getenv('DYNAMODB_PORT', '5102')}"
    )
    _validate_local_endpoint(endpoint)
    table_name = args.table or os.getenv("DYNAMODB_TABLE") or "app"
    static_dir = args.static_dir or ROOT / "static"

    os.environ.setdefault("AWS_ACCESS_KEY_ID", "dummy")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "dummy")
    os.environ.setdefault("APP_STAGE", "local")
    os.environ["AWS_REGION"] = region
    os.environ["DYNAMODB_ENDPOINT"] = endpoint
    os.environ["DYNAMODB_TABLE"] = table_name
    os.environ["STATIC_FILES_DIR"] = str(static_dir)
    if args.apply:
        static_dir.mkdir(parents=True, exist_ok=True)
    target = {
        "stage": "local",
        "region": region,
        "dynamodb_endpoint": endpoint,
        "table": table_name,
        "static_dir": str(static_dir),
        "mode": "apply" if args.apply else "dry-run",
    }
    return target


def configure(args) -> dict:
    env_file = args.env_file or (ROOT / ".env.prod" if args.production else ROOT / ".env")
    load_env_file(env_file)
    if args.production:
        return _configure_production(args)
    return _configure_local(args)


def get_tag_page(query):
    from shared_utils import get_tags

    return get_tags(query)


def candidate_tags(limit: int | None = None) -> list:
    from query_dtos import TagQueryDTO

    result = []
    query = TagQueryDTO(limit=40)
    while True:
        tags = get_tag_page(query)
        for tag in tags:
            if tag.name == slug_to_name(tag.slug) and tag.image_filename:
                continue
            result.append(tag)
            if limit is not None and len(result) >= limit:
                return result
        if not tags or not tags[-1].offset:
            return result
        query = TagQueryDTO(limit=40, offset=tags[-1].offset)


def search_pexels_photo(
        session: requests.Session,
        api_key: str,
        query: str,
        orientation: str,
) -> PexelsPhoto:
    response = session.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={
            "query": query,
            "orientation": orientation,
            "locale": "en-US",
            "page": 1,
            "per_page": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    photos = response.json().get("photos", [])
    if not photos:
        raise ValueError(f"Pexels returned no photos for {query!r}")
    photo = photos[0]
    sources = photo.get("src", {})
    if orientation == "square":
        original_url = sources.get("original")
        image_url = square_image_url(original_url) if original_url else None
    else:
        image_url = sources.get(orientation)
    if not image_url:
        raise ValueError(f"Pexels photo {photo.get('id')} has no {orientation} image")
    remaining = response.headers.get("X-Ratelimit-Remaining")
    reset = response.headers.get("X-Ratelimit-Reset")
    return PexelsPhoto(
        id=int(photo["id"]),
        image_url=image_url,
        page_url=photo["url"],
        photographer=photo.get("photographer", ""),
        photographer_url=photo.get("photographer_url", ""),
        alt=photo.get("alt", ""),
        orientation=orientation,
        rate_limit_remaining=int(remaining) if remaining is not None else None,
        rate_limit_reset=int(reset) if reset is not None else None,
    )


def build_plans(
        session: requests.Session,
        api_key: str,
        limit: int | None,
        request_delay: float = 0,
        on_plan=None,
        on_error=None,
) -> tuple[list[TagPlan], list[dict]]:
    plans = []
    errors = []
    last_request_at = None
    for tag in candidate_tags(limit):
        slug = tag.slug
        name = slug_to_name(slug)
        photo = None
        search_query = None
        if not tag.image_filename:
            search_query = image_search_query(slug)
            orientation = image_orientation(slug)
            try:
                last_request_at = wait_for_pexels_request(last_request_at, request_delay)
                photo = search_pexels_photo(session, api_key, search_query, orientation)
            except requests.RequestException as error:
                item_error = {"slug": slug, "stage": "pexels_search", "error": str(error)}
                errors.append(item_error)
                if on_error:
                    on_error(item_error)
                return plans, errors
            except (KeyError, TypeError, ValueError) as error:
                item_error = {"slug": slug, "stage": "pexels_search", "error": str(error)}
                errors.append(item_error)
                if on_error:
                    on_error(item_error)
                continue
        plan = TagPlan(
            slug=slug,
            current_name=tag.name,
            name=name,
            current_image_filename=tag.image_filename,
            photo=photo,
            image_search_query=search_query,
        )
        plans.append(plan)
        if on_plan:
            on_plan(plan)
    return plans, errors


def download_image(session: requests.Session, plan: TagPlan) -> ImageFile:
    response = session.get(plan.photo.image_url, timeout=60)
    response.raise_for_status()
    return ImageFile(
        content=response.content,
        source_filename=f"{plan.slug}-pexels-{plan.photo.id}.jpg",
    )


def save_image(image: ImageFile) -> str:
    from api_utils import resize_public_image, save_public_file
    from basic_dtos import ImageFileDTO

    image_dto = ImageFileDTO(content=image.content, filename=image.source_filename)
    return save_public_file(resize_public_image(image_dto))


def update_tag_with_service(plan: TagPlan, image_filename: str | None, actor) -> None:
    from api_utils import update_tag
    from prompt_dtos import UpdateTagDTO
    from shared_utils import find_tag

    tag = find_tag(plan.slug)
    if tag is None:
        raise ValueError(f"tag no longer exists: {plan.slug}")
    changes = {
        "name": plan.name,
        "image_action": "keep",
    }
    if image_filename is not None:
        changes.update(image_action="replace", image_filename=image_filename)
    update_tag(tag, UpdateTagDTO(**changes), actor)


def apply_plan(session: requests.Session, plan: TagPlan, actor) -> dict:
    image = download_image(session, plan) if plan.photo else None
    image_filename = save_image(image) if image else None
    update_tag_with_service(plan, image_filename, actor)
    return {
        "slug": plan.slug,
        "name": plan.name,
        "image_filename": image_filename or plan.current_image_filename,
        "pexels_photo": plan.photo.to_dict() if plan.photo else None,
    }


def get_user_page(query):
    from shared_utils import get_users

    return get_users(query)


def resolve_actor(user_id: str | None):
    from query_dtos import UserQueryDTO
    from shared_utils import Permission, find_user

    if user_id:
        actor = find_user(user_id)
        if actor is None:
            raise ValueError(f"user not found: {user_id}")
        return actor

    root_users = []
    query = UserQueryDTO(limit=40)
    while True:
        users = get_user_page(query)
        root_users.extend(
            user for user in users
            if Permission.ROOT in user.permissions or Permission.ALL in user.permissions
        )
        if not users or not users[-1].offset:
            break
        query = UserQueryDTO(limit=40, offset=users[-1].offset)

    if len(root_users) != 1:
        raise ValueError(
            "--user-id is required unless exactly one active root user exists"
        )
    return root_users[0]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Set canonical tag names and fill missing tag images from Pexels."
    )
    result.add_argument(
        "--production",
        action="store_true",
        help="Target production AWS resources; default is local DynamoDB",
    )
    result.add_argument(
        "--apply",
        action="store_true",
        help="Write images and update tags; default is read-only",
    )
    result.add_argument("--limit", type=positive_int, help="Maximum number of tags to process")
    result.add_argument(
        "--pexels-delay",
        type=nonnegative_float,
        default=DEFAULT_PEXELS_DELAY_SECONDS,
        help=f"Seconds between Pexels searches; default is {DEFAULT_PEXELS_DELAY_SECONDS}",
    )
    result.add_argument("--env-file", type=Path, help="Defaults to .env locally or .env.prod in production")
    result.add_argument("--endpoint", help="Local DynamoDB endpoint override")
    result.add_argument("--table", help="DynamoDB table override")
    result.add_argument(
        "--user-id",
        help="User performing applied updates; defaults to TAG_SETUP_USER_ID or the only active root user",
    )
    result.add_argument("--static-dir", type=Path, help="Local image directory; defaults to ./static")
    result.add_argument("--stack", help="Production CloudFormation stack; defaults to AWS_STACK")
    result.add_argument("--media-bucket", help="Production media bucket; normally resolved from the stack")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        target = configure(args)
        api_key = os.getenv("PEXELS_API_KEY")
        if not api_key:
            raise ValueError("PEXELS_API_KEY is required")
        target["pexels_delay_seconds"] = args.pexels_delay

        print(json.dumps({"target": target}, indent=2), flush=True)
        with requests.Session() as session:
            actor = (
                resolve_actor(args.user_id or os.getenv("TAG_SETUP_USER_ID"))
                if args.apply else None
            )
            applied = 0
            apply_errors = []

            def process_plan(plan):
                nonlocal applied
                print(json.dumps({
                    "operation": "would_update_tag",
                    **plan.to_dict(),
                }, indent=2), flush=True)
                if not args.apply:
                    return
                try:
                    result = apply_plan(session, plan, actor)
                    applied += 1
                    print(json.dumps({
                        "operation": "updated_tag",
                        **result,
                    }, indent=2), flush=True)
                except Exception as error:
                    item_error = {"slug": plan.slug, "stage": "apply", "error": str(error)}
                    apply_errors.append(item_error)
                    print(json.dumps({
                        "operation": "error",
                        **item_error,
                    }), file=sys.stderr, flush=True)

            plans, errors = build_plans(
                session,
                api_key,
                args.limit,
                request_delay=args.pexels_delay,
                on_plan=process_plan,
                on_error=lambda error: print(json.dumps({
                    "operation": "error",
                    **error,
                }), file=sys.stderr, flush=True),
            )
            errors.extend(apply_errors)

        summary = {
            "mode": target["mode"],
            "planned": len(plans),
            "applied": applied,
            "errors": len(errors),
        }
        print(json.dumps({"summary": summary}, indent=2), flush=True)
        return 1 if errors else 0
    except (ClientError, requests.RequestException, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
