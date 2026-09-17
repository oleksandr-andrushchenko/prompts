"""Add dimension suffixes and responsive variants to existing prompt JPEGs.

This is a production-only migration and is a dry run unless ``--apply`` is
provided. A dry run reads prompt records and S3 objects, but writes nothing.

Examples (run from the repository root):

    HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
    docker compose -f docker-compose.scripts.production.yml run --rm --build scripts-production \
      python scripts/fix_prompt_jpeg_names.py --production

    # After reviewing the dry-run output:
    HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
    docker compose -f docker-compose.scripts.production.yml run --rm --build scripts-production \
      python scripts/fix_prompt_jpeg_names.py --production --apply

The copied JPEG fires the existing S3 EventBridge rule. After S3 confirms the
new source object was saved, the script conditionally updates that prompt's
DynamoDB record and immediately deletes that prompt's old JPEGs. The image
Lambda generates WebP variants asynchronously from the new source key.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
JPEG_NAME = re.compile(r"^(?P<base>.+)\.(?P<extension>jpe?g)$", re.IGNORECASE)
DIMENSIONED_JPEG_NAME = re.compile(r"^.+_\d+x\d+\.jpe?g$", re.IGNORECASE)
TARGET_WIDTHS = (160, 320, 640, 1024)
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
    "DYNAMODB_TABLE",
    "STATIC_S3_BUCKET",
}


@dataclass(frozen=True)
class FilePlan:
    old_key: str
    new_key: str
    width: int
    height: int
    variants: tuple[str, ...]
    sha256: str
    target_exists: bool

    def to_dict(self):
        return {
            "old_key": self.old_key,
            "new_key": self.new_key,
            "width": self.width,
            "height": self.height,
            "variants": list(self.variants),
            "sha256": self.sha256,
            "target_exists": self.target_exists,
        }


@dataclass(frozen=True)
class PromptPlan:
    prompt_id: str
    key: dict
    old_result_files: list
    new_result_files: list
    files: tuple[FilePlan, ...]

    def to_dict(self):
        return {
            "prompt_id": self.prompt_id,
            "key": self.key,
            "old_result_files": self.old_result_files,
            "new_result_files": self.new_result_files,
            "files": [item.to_dict() for item in self.files],
        }


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ENV_KEYS:
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


def configure(args) -> tuple[dict, object, object]:
    load_env_file(args.env_file)
    if os.getenv("APP_STAGE") != "prod":
        raise ValueError("production migration requires APP_STAGE=prod")

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
        raise ValueError("production migration requires --stack or AWS_STACK")
    outputs = stack_outputs(stack)
    table_name = args.table or outputs.get("DynamoDbTableName") or os.getenv("DYNAMODB_TABLE")
    bucket = args.media_bucket or outputs.get("SiteBucketName") or os.getenv("STATIC_S3_BUCKET")
    if not table_name or not bucket:
        raise ValueError("unable to resolve production DynamoDB table and media bucket")

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
    table = boto3.resource("dynamodb", config=AWS_CONFIG).Table(table_name)
    return target, table, boto3.client("s3", config=AWS_CONFIG)


def read_object(s3, bucket: str, key: str) -> tuple[bytes, dict]:
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        return body.read(), response
    finally:
        body.close()


def get_existing_object(s3, bucket: str, key: str) -> bytes | None:
    try:
        data, _ = read_object(s3, bucket, key)
        return data
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def jpeg_dimensions(data: bytes, key: str) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "JPEG":
            raise ValueError(f"S3 object is not a JPEG: {key}")
        width, height = image.size
        image.verify()
    if width < 1 or height < 1:
        raise ValueError(f"JPEG has invalid dimensions: {key}")
    return width, height


def destination_keys(old_key: str, width: int, height: int) -> tuple[str, tuple[str, ...]]:
    directory, separator, filename = old_key.rpartition("/")
    match = JPEG_NAME.fullmatch(filename)
    if not match:
        raise ValueError(f"not a JPEG key: {old_key}")
    prefix = f"{directory}/" if separator else ""
    base = match.group("base")
    extension = match.group("extension").lower()
    new_key = f"{prefix}{base}_{width}x{height}.{extension}"
    variants = [
        f"{prefix}{base}_{target_width}x{round(target_width * height / width)}.webp"
        for target_width in TARGET_WIDTHS
        if target_width < width
    ]
    variants.append(f"{prefix}{base}_{width}x{height}.webp")
    return new_key, tuple(variants)


def scan_prompt_items(table):
    scan_args = {
        "FilterExpression": (
            Attr("pk").begins_with("PROMPT#")
            & Attr("sk").eq("META")
            & Attr("result_files").exists()
        ),
        "ProjectionExpression": "#pk, #sk, id, result_files",
        "ExpressionAttributeNames": {"#pk": "pk", "#sk": "sk"},
    }
    page = 0
    scanned = 0
    matched = 0
    while True:
        response = table.scan(**scan_args)
        page += 1
        scanned += response.get("ScannedCount", 0)
        items = response.get("Items", [])
        matched += len(items)
        print(json.dumps({
            "operation": "scan_progress",
            "page": page,
            "items_scanned": scanned,
            "prompt_items_with_results": matched,
        }), flush=True)
        yield from items
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_args["ExclusiveStartKey"] = last_key


def is_legacy_jpeg(filename) -> bool:
    return (
        isinstance(filename, str)
        and "://" not in filename
        and JPEG_NAME.fullmatch(filename.rsplit("/", 1)[-1]) is not None
        and DIMENSIONED_JPEG_NAME.fullmatch(filename.rsplit("/", 1)[-1]) is None
    )


def build_file_plan(s3, bucket: str, old_key: str) -> FilePlan:
    source, _ = read_object(s3, bucket, old_key)
    width, height = jpeg_dimensions(source, old_key)
    new_key, variants = destination_keys(old_key, width, height)
    target = get_existing_object(s3, bucket, new_key)
    if target is not None and target != source:
        raise ValueError(f"destination exists with different content: {new_key}")
    return FilePlan(
        old_key=old_key,
        new_key=new_key,
        width=width,
        height=height,
        variants=variants,
        sha256=hashlib.sha256(source).hexdigest(),
        target_exists=target is not None,
    )


def build_plans(table, s3, bucket: str) -> tuple[list[PromptPlan], list[dict]]:
    plans = []
    errors = []
    file_plans = {}
    file_errors = {}

    for item in scan_prompt_items(table):
        old_results = item.get("result_files")
        if not isinstance(old_results, list):
            errors.append({"prompt_id": item.get("id"), "error": "result_files is not a list"})
            continue
        legacy_keys = []
        for result in old_results:
            if (
                isinstance(result, dict)
                and result.get("format") == "image"
                and is_legacy_jpeg(result.get("filename"))
            ):
                legacy_keys.append(result["filename"])
        if not legacy_keys:
            continue

        prompt_files = []
        for old_key in dict.fromkeys(legacy_keys):
            if old_key not in file_plans and old_key not in file_errors:
                print(json.dumps({
                    "operation": "inspect_jpeg",
                    "prompt_id": item.get("id"),
                    "key": old_key,
                }), flush=True)
                try:
                    file_plans[old_key] = build_file_plan(s3, bucket, old_key)
                    print(json.dumps({
                        "operation": "inspected_jpeg",
                        **file_plans[old_key].to_dict(),
                    }), flush=True)
                except Exception as error:
                    file_errors[old_key] = str(error)
            if old_key in file_errors:
                errors.append({
                    "prompt_id": item.get("id"),
                    "filename": old_key,
                    "error": file_errors[old_key],
                })
            else:
                prompt_files.append(file_plans[old_key])
        if len(prompt_files) != len(set(legacy_keys)):
            continue

        replacements = {file.old_key: file.new_key for file in prompt_files}
        new_results = [
            {**result, "filename": replacements.get(result.get("filename"), result.get("filename"))}
            if isinstance(result, dict) and result.get("format") == "image" else result
            for result in old_results
        ]
        plans.append(PromptPlan(
            prompt_id=item.get("id") or item["pk"].removeprefix("PROMPT#"),
            key={"pk": item["pk"], "sk": item["sk"]},
            old_result_files=old_results,
            new_result_files=new_results,
            files=tuple(prompt_files),
        ))
    return plans, errors


def copy_source(s3, bucket: str, plan: FilePlan) -> None:
    s3.copy_object(
        Bucket=bucket,
        Key=plan.new_key,
        CopySource={"Bucket": bucket, "Key": plan.old_key},
        MetadataDirective="COPY",
        TaggingDirective="COPY",
    )


def prepare_prompt_files(s3, bucket: str, plan: PromptPlan) -> list[FilePlan]:
    prepared = []
    for index, file in enumerate(plan.files, start=1):
        print(json.dumps({
            "operation": "copy_source_for_variant_generation",
            "prompt_id": plan.prompt_id,
            "progress": f"{index}/{len(plan.files)}",
            **file.to_dict(),
        }), flush=True)
        copy_source(s3, bucket, file)
        prepared.append(file)
    return prepared


def update_prompt(table, plan: PromptPlan) -> None:
    table.update_item(
        Key=plan.key,
        UpdateExpression="SET #result_files = :new_result_files",
        ConditionExpression="#result_files = :old_result_files",
        ExpressionAttributeNames={"#result_files": "result_files"},
        ExpressionAttributeValues={
            ":old_result_files": plan.old_result_files,
            ":new_result_files": plan.new_result_files,
        },
    )
    print(json.dumps({
        "operation": "updated_prompt",
        "prompt_id": plan.prompt_id,
        "result_files": plan.new_result_files,
    }), flush=True)


def delete_old_sources(s3, bucket: str, files: list[FilePlan]) -> None:
    for file in files:
        s3.delete_object(Bucket=bucket, Key=file.old_key)
        print(json.dumps({"operation": "deleted_old_source", "key": file.old_key}), flush=True)


def find_shared_files(plans: list[PromptPlan]) -> dict[str, list[str]]:
    prompt_ids_by_file = {}
    for plan in plans:
        for file in plan.files:
            prompt_ids_by_file.setdefault(file.old_key, []).append(plan.prompt_id)
    return {
        key: prompt_ids
        for key, prompt_ids in prompt_ids_by_file.items()
        if len(prompt_ids) > 1
    }


def migrate_prompts(
        table, s3, bucket: str, plans: list[PromptPlan]) -> tuple[int, int, list[dict]]:
    updated = 0
    deleted = 0
    errors = []
    for index, plan in enumerate(plans, start=1):
        print(json.dumps({
            "operation": "migrate_prompt",
            "progress": f"{index}/{len(plans)}",
            "prompt_id": plan.prompt_id,
        }), flush=True)
        try:
            prepared = prepare_prompt_files(s3, bucket, plan)
        except Exception as error:
            errors.append({
                "prompt_id": plan.prompt_id,
                "stage": "prepare_files",
                "error": str(error),
            })
            continue
        try:
            update_prompt(table, plan)
            updated += 1
        except Exception as error:
            errors.append({
                "prompt_id": plan.prompt_id,
                "stage": "update_prompt",
                "error": str(error),
            })
            continue
        try:
            delete_old_sources(s3, bucket, prepared)
            deleted += len(prepared)
        except Exception as error:
            errors.append({
                "prompt_id": plan.prompt_id,
                "stage": "delete_old_sources",
                "error": str(error),
            })
    return updated, deleted, errors


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--production",
        action="store_true",
        help="Required acknowledgement that this targets production AWS resources",
    )
    result.add_argument(
        "--apply",
        action="store_true",
        help="Copy JPEGs, update prompts, and delete old sources; default is read-only",
    )
    result.add_argument("--env-file", type=Path, default=ROOT / ".env.prod")
    result.add_argument("--stack", help="CloudFormation stack; defaults to AWS_STACK")
    result.add_argument("--table", help="DynamoDB table; normally resolved from the stack")
    result.add_argument("--media-bucket", help="S3 bucket; normally resolved from the stack")
    return result


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    if not args.production:
        cli.error("--production is required")

    try:
        target, table, s3 = configure(args)
        print(json.dumps({"target": target}, indent=2), flush=True)
        plans, errors = build_plans(table, s3, target["media_bucket"])
        shared_files = find_shared_files(plans)
        for key, prompt_ids in shared_files.items():
            errors.append({
                "filename": key,
                "prompt_ids": prompt_ids,
                "error": "old JPEG is referenced by multiple prompts",
            })
        for plan in plans:
            print(json.dumps({"operation": "would_update_prompt", **plan.to_dict()}, indent=2))
        for error in errors:
            print(json.dumps({"operation": "preflight_error", **error}), file=sys.stderr)
        summary = {
            "mode": target["mode"],
            "prompts": len(plans),
            "unique_jpegs": len({file.old_key for plan in plans for file in plan.files}),
            "preflight_errors": len(errors),
        }
        if errors:
            print(json.dumps({"summary": summary}, indent=2))
            return 1
        if not args.apply:
            print(json.dumps({"summary": summary}, indent=2))
            return 0

        updated, deleted, migration_errors = migrate_prompts(
            table,
            s3,
            target["media_bucket"],
            plans,
        )
        summary.update(
            updated_prompts=updated,
            deleted_old_jpegs=deleted,
            migration_errors=len(migration_errors),
        )
        for error in migration_errors:
            print(json.dumps({"operation": "migration_error", **error}), file=sys.stderr)
        print(json.dumps({"summary": summary}, indent=2))
        return 1 if migration_errors else 0
    except Exception as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
