# Prompts

## Prerequisites

- docker & docker compose have to be installed
- AWS account
- AWS CLI installed and configured
    - You should have these files: `~/.aws/credentials` and `~/.aws/config`

## Available commands

```
  aws-login            Obtain AWS auth token
  clean                Remove build artifacts
  create-local-dynamodb Create local DynamoDB table
  create-local-dynamodb-dummy-fixtures Populate local DynamoDB with dummy data
  delete-cert-infra    Delete cert CF stack
  delete-code-infra    Delete code CF stack
  delete-infra         Delete CF stack
  deploy               Deploy certificates, code bucket, Lambdas, application, and static files
  deploy-cert-infra    Deploy ACM certificate for the domain
  deploy-code-files    Zip and upload Lambda code to S3
  deploy-web-lambda    Build, upload, and deploy only the Web Lambda
  deploy-api-lambda    Build, upload, and deploy only the API Lambda
  deploy-img-lambda    Build, upload, and deploy only the Image Lambda
  deploy-code-infra    Deploy S3 bucket for Lambda / CloudFront code
  deploy-infra         Deploy CF stack for the site
  deploy-site-files    Sync local site files to S3
  down                 Stop local Docker containers
  drop-local-dynamodb  Drop DynamoDB table in local DynamoDB
  fetch-local-dynamodb Fetch 100 records from local DynamoDB
  generate-code-files  Build all Lambda zips
  generate-web-lambda-code-files  Build the Web Lambda zip
  generate-api-lambda-code-files  Build the API Lambda zip
  generate-img-lambda-code-files  Build the Image Lambda zip
  # Individual deploy-* targets also upload the selected artifact and update only that Lambda
  generate-site-files  Run content generator inside Docker container
  get-cert-arn         Show the CloudFront ACM certificate ARN
  get-cert-infra       Show cert CF stack events
  get-code-infra       Show code CF stack events
  get-infra            Show CF stack events
  help                 Show this help
  invalidate           Invalidate CloudFront cache for the site
  login                Open shell in Docker container
  login-scripts        Open shell in scripts Docker container
  logs                 Show logs of Docker container
  open                 Show local site URL
  rebuild              Rebuild and start Docker containers
  recreate-local-dynamodb Recreate DynamoDB table in local DynamoDB & populate dummy data
  restart              Restart local Docker containers
  tail-scripts-logs    Tail scripts logs
  tests                Run the test suite in the isolated test Docker Compose stack
  up                   Start local Docker containers
```

## AWS deployment

Use `.env.example` as the template for both environment files. Keep local
development values in `.env`, and configure production deployment values in
`.env.prod`, including the existing public Route 53 hosted zone, domain,
application settings, and AWS profile/region. Both files are ignored by Git.

The single `Makefile` retrieves each value from its intended file without
including or exporting either file wholesale. Local Docker settings, ports, and
the local DynamoDB region come from `.env`. AWS, application, domain, and
deployment settings come from `.env.prod`. Lambda ZIP timestamps are stored in
`.env.prod`, including when a standalone `generate-*-lambda-code-files` command
is used.

To use another production environment file for a command, override its path:

```sh
make PROD_ENV_FILE=.env.staging deploy
```

Authenticate the AWS CLI first (`make aws-login` when needed), then run:

```sh
make deploy
```

The command runs these steps sequentially, including with `make -j`:

1. Deploy `cf-cert.yml` in `us-east-1` and wait for the `static.${DOMAIN_NAME}` CloudFront certificate.
2. Deploy `cf-code.yml` in `AWS_REGION` to create the Lambda artifact bucket.
3. Build and upload all three Lambda ZIPs.
4. Read the CloudFront certificate ARN from its stack output and deploy `cf.yml`
   in `AWS_REGION`, including the API certificate and application resources.
5. Build and upload static files after the application creates the site bucket. The
   website is served directly by API Gateway at `${DOMAIN_NAME}`, while CloudFront
   serves S3 assets from `static.${DOMAIN_NAME}`.

During the first migration from the root-domain CloudFront distribution, the old
`us-east-1` root-domain certificate is retained so CloudFormation can finish the
alias cutover. After the deployment succeeds and CloudFront reports `Deployed`,
that unused certificate can be deleted manually from ACM.

## Lambda layout

- `shared/` — shared backend code and templates
- `web-lambda/` — website Lambda handler and dependencies
- `api-lambda/` — API Lambda

API endpoints are exposed through the dedicated `api.${DOMAIN_NAME}` API Gateway
custom domain, with no `/api` path prefix.

- `img-lambda/` — S3 image variant Lambda

## Importing prompts.chat content

The importer combines every logical row from a pinned `prompts.csv` commit with
a cached snapshot of every record returned by the prompts.chat API. Exact
title/content matches are enriched with API metadata, and CSV-only and API-only
records are retained. It uses the application's `create_prompt` and
`update_prompt_status` services, so successful imports are published with normal
owner counters, activity, tags, and slug records.

Local dry run (with the scripts container running):

```sh
docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
  python scripts/import_prompts_chat.py --user-id USER_ID \
  --default-models openai-gpt-* \
  --offset 0
```

The first dry run resolves a full Git commit SHA, saves the pinned CSV and API
snapshot under `.tmp/prompts-chat/`, and records it as the latest completed dry
run. Every item prints the original CSV/API
source, the exact proposed insert/update, and importer comments. `--limit` is
optional and the default processes the full combined source.

For a host Python environment, install `scripts/requirements.txt` and run:

```sh
python scripts/import_prompts_chat.py --user-id USER_ID \
  --default-models openai-gpt-* --apply
```

Local mode explicitly uses dummy credentials and a local DynamoDB endpoint:
`DYNAMODB_ENDPOINT`, or `http://localhost:${DYNAMODB_PORT:-5102}`. Override with
`--endpoint`; local mode rejects remote hosts. The local table defaults to `app`.
The importer reads local settings from `.env` when present.

Production uses a separate, ephemeral scripts service. It reads `.env.prod`,
mounts the host AWS profile, and resolves the DynamoDB table and media bucket
from `AWS_STACK` CloudFormation outputs. The normal `scripts` service has only
local dummy AWS credentials and no host AWS credential mount.

```sh
docker compose -f docker-compose.scripts.production.yml run --rm scripts-production \
  python scripts/import_prompts_chat.py --production \
  --user-id PRODUCTION_OWNER_USER_ID \
  --root-user-id PRODUCTION_ROOT_USER_ID \
  --default-models openai-gpt-*
```

Add `--apply` only after reviewing that production dry run. Without `--commit`,
the importer automatically reuses the latest completed dry-run snapshot, keeping
all four local/production runs on the same inputs. Use `--refresh-source` on a
new dry run when you intentionally want to move to the current upstream data;
`--commit FULL_SHA` remains available to select or replay a specific revision.
`--user-id` owns and creates the prompts.
`--root-user-id` performs publishing and other non-regular importer operations;
it defaults to `--user-id` when the owner is already root.
The intended sequence is:

```sh
# 1. Local dry run; this establishes the latest dry-run snapshot.
docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
  python scripts/import_prompts_chat.py --user-id LOCAL_OWNER_USER_ID \
  --root-user-id LOCAL_ROOT_USER_ID

# 2. Local apply automatically uses exactly that snapshot.
docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
  python scripts/import_prompts_chat.py --user-id LOCAL_OWNER_USER_ID \
  --root-user-id LOCAL_ROOT_USER_ID \
  --apply

# 3. Production dry run using the isolated production scripts service.
docker compose -f docker-compose.scripts.production.yml run --rm scripts-production \
  python scripts/import_prompts_chat.py --production \
  --user-id PRODUCTION_OWNER_USER_ID --root-user-id PRODUCTION_ROOT_USER_ID

# 4. Production apply.
docker compose -f docker-compose.scripts.production.yml run --rm scripts-production \
  python scripts/import_prompts_chat.py --production \
  --user-id PRODUCTION_OWNER_USER_ID --root-user-id PRODUCTION_ROOT_USER_ID --apply
```

Use `--default-models MODEL...` on all four commands only if prompts without an
upstream recommendation should receive an operator-selected family. Redirecting
stdout to a file is useful because the full dry run intentionally prints every
source record and proposed target record.

### Deduplication and metadata

`Prompt.source` preserves provenance, upstream IDs and timestamps, the original
type/category/tags, sanitized author/contributors, model recommendations and
their mapping origin, moderation/featured state, media declarations, MCP/workflow
metadata, the CSV commit, and API snapshot time.
`act` maps to `title`. Each Prompt contains exactly one reusable template and
named input/output declarations:

```json
{
  "template": {"content": "Describe ${product_details} for an image generator.", "format": "text"},
  "inputs": [{"name": "product_details", "formats": ["text"], "required": true}],
  "outputs": [{"name": "description", "formats": ["text"]}]
}
```

- `template.content` is the original prompt body, up to 300,000 UTF-8 bytes.
- `template.format` describes its representation: text, Markdown, HTML, JSON,
  YAML, XML, CSV, or code. An image-generating prompt can have a structured template.
- `inputs` names the values or media needed by the prompt. Each has `name`,
  accepted `formats`, an optional `description`, and `required` (default true).
  Optional text inputs may also define a string `default` of up to 1,000 bytes.
- `outputs` names the results the prompt can produce. Each has `name`, possible
  `formats`, and an optional `description`. These declarations are separate from
  example files (`result_files`).

Names use letters, digits, and underscores, starting with a letter or underscore,
up to 64 characters. Names must be unique within each list. Formats include text,
Markdown, HTML, JSON, YAML, XML, CSV, code, image, video, audio, and document.
An empty `formats` list means unspecified. Several formats on one input are
accepted alternatives; several on one output are possible result formats. Use
separate named outputs when the prompt produces separate artifacts.

`${parameter-name}` is the canonical parameter syntax;
`${parameter-name:default value}` adds an optional default. On create/import/update,
parameter names are normalized to lowercase kebab-case while syntax and defaults
are retained, so `${Mother Language:Turkish}` becomes
`${mother-language:Turkish}`. The application extracts unique parameters and their defaults into
the derived `Prompt.params` attribute. Older records derive the same attribute on
read. Parameter declarations are shown on the prompt page, and parameterized
prompts receive a dedicated badge.

Source TEXT/IMAGE/VIDEO/AUDIO/DOCUMENT map directly to result formats. Structured
content is detected as HTML, JSON, YAML, XML, Markdown, or plain text independently of its
output. Source parameters become derived `params`; explicitly mentioned reference
media become named media inputs. When the exact prompts.chat API record
requires a media upload, `requiredMediaType` and `requiredMediaCount` add one or
more required `reference_<format>` inputs. These are heuristic inferences, so
review the declarations after importing.
API type and `structuredFormat` take precedence over the CSV. Delisted records,
SKILL, and TASTE records are skipped by default; the latter two have no matching
ordinary-prompt contract. Use `--include-delisted` or `--include-incompatible`
only when that flattening is intentional. Titles support the upstream 200-character
limit, descriptions support 500 characters, and oversized bodies are reported.

The API and DynamoDB records use `template`, `inputs`, `outputs`, and
`result_files` directly. Old field names are not converted on read or accepted in
write DTOs. Persisted references use stable internal keys: categories use
`PromptCategory` values such as `design-image`, formats use `PromptFormat` values
such as `image`, models use `PromptModel` values such as `openai-gpt-4o`,
and prompt tags use `Tag.slug`. Category labels such as `Design & Image` are
resolved only for display.

Metadata is derived without LLM calls in `scripts/import_prompt_metadata.py`:

- API descriptions are preferred; otherwise descriptions are derived from the
  prompt and fit the catalog's 500-character limit.
- Categories use phrase rules mapped to `PromptCategory`, with stronger title
  matches and the opening 12,000 characters of the body. Close scores or unmatched prompts fall back to `other` and emit an
  explicit warning with the top category candidates and their scores.
- Tags use a controlled vocabulary with synonyms, prefer title matches, and keep
  up to three supported tags. No matched tags produces a warning, not a source tag.

`scripts/import_prompts_chat_overrides.json` contains curated descriptions, categories,
tags, and output mappings keyed by slug. Use `--overrides PATH` to supply another
JSON file. Overrides take precedence over rules; unspecified fields still use
rules. All entries are validated through `PromptDTO` before processing. Example:

```json
{
  "linux-terminal": {
    "description": "Simulate a Linux terminal and respond with command output.",
    "category": "code-dev",
    "tags": ["linux", "terminal-simulation"],
    "outputs": [{"name": "result", "formats": ["text"]}],
    "template_format": "text",
    "inputs": [{"name": "input", "formats": ["text"], "required": true}]
  }
}
```

Rules are heuristic, not verified semantic classifications. Review the printed
metadata warnings and add overrides for ambiguous records. Prompt content,
including parameter spelling and defaults, is preserved; description cleanup does
not alter the template.
API `bestWithModels` recommendations are preserved verbatim in
`source.best_with_models` and mapped to catalog model values when supported.
`--default-models` is optional and is used only when no upstream recommendation
can be mapped. With no fallback, an empty model list honestly means unspecified.
Catalog model values are provider-qualified. Family values ending in `-*`, such
as `openai-gpt-*`, `openai-gpt-5-*`, `openai-gpt-image-*`, and
`openai-gpt-audio-*`, represent compatibility with an unknown or any version in
that family. Unknown future exact members map to the closest known family. The
prompts.chat spellings without provider prefixes (for example, `gpt-5-*`,
`claude-4-5-opus`, and `sora 2`) are accepted and normalized to the corresponding
catalog values.

Uniqueness uses the owner ID plus the catalog's title-derived slug
(`to_kebab_case`), matching URLs shaped as `/@user-slug/prompt-slug`. Different
users may therefore use the same prompt slug, while one owner cannot use the
same slug twice. The importer checks slugs already seen in its owner-specific
batch and batch-reads that owner's existing slug records from DynamoDB. Existing
unrelated slugs owned by that import account are skipped. An earlier
prompts.chat import left unpublished is published on resume. `create_prompt` writes the slug record with
`attribute_not_exists(pk)` in the same transaction as the prompt and counters,
so concurrent imports for the same owner cannot create the same slug twice. No
separate title or content hash records are created; identical content under
different owner/slug paths is allowed.

Import behavior is create-if-absent and publish: existing published imports are
no-ops, preserving catalog edits even if upstream changes. The sole derived-data
reconciliation is `params`: a rerun backfills it from the existing stored template
without replacing that template or other catalog fields. Pre-feature
prompts.chat records that lack the `params` attribute are upgraded once from the
same pinned source, restoring its template with canonical parameter names and
separating parameters from ordinary inputs. A renamed upstream
title producing a new slug is treated as a new prompt. Offsets apply to the pinned
combined snapshot.

Final statistics include CSV/API/combined and match/CSV-only/API-only totals,
scanned/prepared/created/published/resumed/would-create/would-publish/unchanged/
would-resume/skipped/error counts, declared/planned/copied media totals, reasons,
source types, and model-assignment origins.

### Importing example results

The importer fetches the paginated API once per new snapshot and joins it to the
CSV locally. It imports every unique supported `mediaUrl` and user-example
attachment; it does not run prompts or generate new media.

Dry runs list planned attachments without downloading or saving them. With
`--apply`, images go through `ImageFileDTO` and
`save_public_file` into the existing image gallery. Video, audio, and plain-text
attachments also use `save_public_file`. All examples are stored in the single
`PromptDTO.result_files` list; the prompt page
provides video/audio playback and download links. Local files go to `static/`.
Production resolves `STATIC_S3_BUCKET` from the stack or accepts
`--media-bucket BUCKET_NAME`.

The importer accepts HTTPS media from the finite set of hosts currently referenced
by the prompts.chat API, rejects redirects, and checks downloaded file signatures
against supported media types. It reads an extension from the URL path or a
`format` query parameter. Images support JPEG, PNG, GIF, and WebP. Imported media
is capped at 50 MiB per file without raising the normal interactive upload limit. Unsupported or newly
introduced formats/hosts are reported and omitted until reviewed. A download or save failure
stops that record; files saved before prompt creation are removed on failure.
Every stored attachment passes through `save_public_file`. `media_found` and
`media_copied` are included in run statistics.

The source's [terms](https://prompts.chat/terms) explicitly apply CC0 to generated
media.

## TODO

- optimize Projections for DynamoDB indexes
- optimize DynamoDB attributes
- map app's endpoints to api gateway
- delete public images func?
- add users email/sms notifications (prompt published/liked/disliked, user followed/blocked etc.)
- add meta info for tags and images (created_by, created_at)
- add aria attributes (+allow them in tinymce)
- add footer tag for prompt/prompts, put related prompts (Like "Futher reading", based on tags)
- replace env secrets with secrets manager storage (CS becomes slower)
- jpeg images have problems with dimensions determination (on uploads)
- add image watermarks
- add author to the footer
- update logo in google auth
- prompts page: add popular tags to "filter by tags" block
- improve prompt comments
- prompts form: submit slugs URL version (instead of queries)
- generate tag combos for prompt pages (prompt's tag combos for crawlers)
- remove personal contact details
- add user_name and user_slug attributes to prompts, render user in prompt fragments, sync when user changed
- tinymce: on image change - call api to drop the old image
- content on prompt edit page is not editable
- cover all the avaiable web/API endpoints with integrations tests
- refactor prompt voting: vote from 0 to 5 (by star selection), user rating recalculated from prompt rating
- tags aliases: for example: cache=caching, cdn=content-delivery-network, etc.
- prompt page: similar prompts section shows no the all prompts
- prompt page: auto append/generate "More Prompts to Read" paragraph
- file uploader with preview and TinyMCE image upload by URL

## Links

- favicon - https://realfavicongenerator.net

## Telegram administrator notifications

The application uses standard Python logging with a console handler and an optional
`TelegramHandler`. Business events use `logger.info(..., extra={...})`; failures
use `logger.error()` or `logger.exception()`. Application code does not call
Telegram directly. The handler attaches once to the `app` logger; child loggers
propagate to it. Third-party library logs are excluded.
This follows Python's [logger/handler model](https://docs.python.org/3/howto/logging.html#advanced-logging-tutorial).

Create a bot with [BotFather](https://t.me/BotFather), start a private chat with
it (or add it to your administrator group), and send it a message. Use the Bot
API's [getUpdates](https://core.telegram.org/bots/api#getupdates) method to find
that message's `chat.id`. Keep the token private; do not commit it.

Set these values in your local `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
TELEGRAM_LOG_LEVEL=INFO
```

`TELEGRAM_LOG_LEVEL` controls Telegram independently of the console threshold:

| Level | Records delivered |
| --- | --- |
| DEBUG | All application logs, including request diagnostics |
| INFO (default) | Activity, other informational logs, warnings and errors |
| WARNING | Warnings, errors and critical failures |
| ERROR | Errors and critical failures |
| CRITICAL | Critical failures only |
| OFF | None |

Missing credentials disable the handler. Invalid levels disable it with a console
diagnostic. This replaces `TELEGRAM_EVENTS_ENABLED` / `TELEGRAM_ERRORS_ENABLED`.
Recreate Docker Compose web/API containers after changing configuration. For AWS,
build/upload both Lambdas and run `make deploy-infra` (or use `make deploy`).
The CloudFormation bot-token parameter uses `NoEcho`.

Activity records cover newly saved users, prompts, comments, contact messages,
and prompt status changes. Existing-user logins do not log registration events.
Web/API exception handlers log unexpected exceptions and HTTP 5xx exceptions at
ERROR, and handled HTTP 4xx exceptions at INFO. Returning a 5xx response directly
does not trigger an exception handler; log the failure where it occurs. Existing logged failures, including publication email failures, also
reach Telegram at the configured level. Handled HTTP 4xx diagnostics use INFO.

The Telegram formatter includes stage, severity, logger name, message, exception
class, and supported record IDs/request context. HTTP errors include the method,
path, client IP, user agent, service and request ID. Query strings, cookies and
authorization headers are excluded. The client IP comes from the ASGI connection
(API Gateway `requestContext.http.sourceIp` in Lambda), not arbitrary forwarded
headers; behind a proxy it may identify the proxy. Full tracebacks remain in server
logs. Event messages exclude content bodies and contact details; keep credentials
and private data out of log messages. The handler redacts its bot token and does
not forward exception text, stack traces or arbitrary extra fields.

Delivery uses [sendMessage](https://core.telegram.org/bots/api#sendmessage), is
best effort, and runs synchronously with a two-second network timeout. It can add
latency per record. There is no background thread, retry queue, or guaranteed
delivery; outages and Telegram rate limits can drop alerts. Delivery errors write
a fixed diagnostic to stderr without re-entering logging or failing the request.
For high-volume durable delivery, use a separate worker/queue or CloudWatch log
subscription rather than an in-process background logging thread.

Image Lambda failures, startup failures and hard timeouts are outside these
web/API application logging hooks.

Run offline logging checks with:
`python3 -m unittest discover -s tests -p test_notifications.py`.
Exception-handler routing checks are in `tests/test_exception_handlers.py` and
run with the normal test suite (they require the application dependencies).


Prompt examples use one `result_files` list:

```json
{
  "result_files": [
    {"filename": "example.png", "format": "image"},
    {"filename": "demo.mp4", "format": "video"},
    {"filename": "speech.mp3", "format": "audio"},
    {"filename": "answer.txt", "format": "text"}
  ]
}
```

Images supply gallery images, thumbnails, and social previews. Existing HTTP(S)
image URLs are also supported. Other formats use local asset filenames. Editing
images preserves non-image examples; the API can replace the full list, or clear
it with `result_files: []`.
