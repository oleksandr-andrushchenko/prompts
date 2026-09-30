import json
import os
from pathlib import Path


def _get_live_config():
    return {
        "app_stage": os.getenv("APP_STAGE"),
        "app_env": os.getenv("APP_ENV"),
        "app_debug": os.getenv("APP_DEBUG"),
        "app_secret": os.getenv("APP_SECRET"),
        "web_base_url": os.getenv("WEB_BASE_URL"),
        "api_base_url": os.getenv("API_BASE_URL"),
        "static_base_url": os.getenv("STATIC_BASE_URL"),
        "aws_region": os.getenv("AWS_REGION"),
        "dynamodb_endpoint": os.getenv("DYNAMODB_ENDPOINT"),
        "dynamodb_table": os.getenv("DYNAMODB_TABLE"),
        "google_analytics_id": os.getenv("GOOGLE_ANALYTICS_ID"),
        "tinymce_api_key": os.getenv("TINYMCE_API_KEY"),
        "contact_topic_arn": os.getenv("CONTACT_TOPIC_ARN"),
        "ses_from_email": os.getenv("SES_FROM_EMAIL"),
        "allowed_origin": os.getenv("ALLOWED_ORIGIN"),
        "cognito_domain": os.getenv("COGNITO_DOMAIN"),
        "cognito_client_id": os.getenv("COGNITO_CLIENT_ID"),
        "cognito_client_secret": os.getenv("COGNITO_CLIENT_SECRET"),
        "cognito_user_pool_id": os.getenv("COGNITO_USER_POOL_ID"),
        "email_files_dir": os.getenv("EMAIL_FILES_DIR", "/app-emails"),
        "static_files_dir": os.getenv("STATIC_FILES_DIR", "/app-static"),
        "css_cache_counter": os.getenv("CSS_CACHE_COUNTER", 0),
        "js_cache_counter": os.getenv("JS_CACHE_COUNTER", 0),
        "auth_token_max_age": os.getenv("AUTH_TOKEN_MAX_AGE", 86_400 * 7),
        "auth_jwt_secret": os.getenv("AUTH_JWT_SECRET"),
        "cloudformation_districution_id": os.getenv("CLOUDFRONT_DISTRIBUTION_ID"),
        "static_s3_bucket": os.getenv("STATIC_S3_BUCKET"),
        "function_templates_dir": os.getenv("FUNCTION_TEMPLATES_DIR"),
        "permission_hierarchy": {
            "regular": [
                "update-user-impression",
                "create-post",
                "toggle-prompt-impression",
                "create-prompt-comment",
                "create-contact-message",
            ],
            "root": ["*"],
        },
        "default_avatar_colors": {
            "A": "#F44336",
            "B": "#E91E63",
            "C": "#9C27B0",
            "D": "#673AB7",
            "E": "#3F51B5",
            "F": "#2196F3",
            "G": "#03A9F4",
            "H": "#00BCD4",
            "I": "#009688",
            "J": "#4CAF50",
            "K": "#8BC34A",
            "L": "#CDDC39",
            "M": "#FFEB3B",
            "N": "#FFC107",
            "O": "#FF9800",
            "P": "#FF5722",
            "Q": "#795548",
            "R": "#9E9E9E",
            "S": "#607D8B",
            "T": "#FF1744",
            "U": "#D500F9",
            "V": "#00E676",
            "W": "#00B0FF",
            "X": "#FFD600",
            "Y": "#FF6D00",
            "Z": "#C51162",
        },
        **json.loads(Path(__file__).with_name("data.default.json").read_text()),
        **json.loads(Path(__file__).with_name("data.json").read_text()),
    }


config = _get_live_config()


def get_config():
    return config
