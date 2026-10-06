import base64
import decimal
import json
import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

root_dir = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent))


@lru_cache
def get_web_request():
    """Return a request backed by the web route registry for scripts."""
    from web import Application, Request
    from web_route_metadata import WEB_URL_ROUTES

    app = Application()
    for name, path in WEB_URL_ROUTES.items():
        app.add_url_route(path, name)

    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "root_path": "",
        "query_string": b"",
        "scheme": "https",
        "server": ("localhost", 443),
        "client": ("127.0.0.1", 0),
        "headers": [],
        "app": app,
    })


def get_dynamodb_schema() -> dict:
    # Ignore unknown CF tags like !Sub, !Ref
    def ignore_unknown(loader, tag_suffix, node):
        return loader.construct_scalar(node)

    yaml.add_multi_constructor("!", ignore_unknown)

    with open(root_dir / "cf.yml", "r") as f:
        cf = yaml.load(f, Loader=yaml.FullLoader)

    props = cf.get("Resources", {}).get("DynamoDBTable", {}).get("Properties", {})

    # Keep only DynamoDB keys
    allowed_keys = {"TableName", "BillingMode", "AttributeDefinitions", "KeySchema", "GlobalSecondaryIndexes"}
    return {k: v for k, v in props.items() if k in allowed_keys}


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            # you can cast to int if you know it’s always an integer
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super().default(o)


def encode_offset(offset: dict) -> str | None:
    if not offset:
        return None
    return base64.urlsafe_b64encode(
        json.dumps(offset, cls=DecimalEncoder).encode()
    ).decode()
