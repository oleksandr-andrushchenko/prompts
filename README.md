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

## Setting up tag names and images

`scripts/setup_tags.py` converts stored tag slugs to display names and fills
missing tag images with the first Pexels result for that name from the
official Pexels API. Existing images are preserved. Add `PEXELS_API_KEY` to
`.env` for local runs and `.env.prod` for production runs.

The safe defaults are a local DynamoDB target and a dry run:

```sh
docker compose -f docker-compose.yml -f docker-compose.scripts.yml exec scripts \
  python scripts/setup_tags.py --limit 10
```

Review the JSON plan, then add `--apply` to write the local images and tag
updates. Omit `--limit` to process every tag that needs a name or image. Applied
runs use the only active root user automatically; pass `--user-id` or set
`TAG_SETUP_USER_ID` when that is ambiguous. Pexels searches are spaced 18.5
seconds apart by default to remain below the documented 200 requests/hour
limit; use `--pexels-delay` only when a different approved limit applies.

Production is selected explicitly and remains a dry run without `--apply`:

```sh
HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
docker compose -f docker-compose.scripts.production.yml run --rm scripts-production \
  python scripts/setup_tags.py --production --limit 10
```

Each planned and applied image includes its Pexels page, photographer, and
photographer profile in the JSON output for provenance and attribution.

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
- prompts file uploader upload -> remove -> upload bug
- send newly created content's links to search-engines

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
