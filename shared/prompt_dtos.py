from dataclasses import dataclass, field
from enum import StrEnum

from basic_dtos import BaseDTO, UNSET
from query_dtos import PromptStatus


def _validate_tags(values):
    from shared_utils import to_kebab_case
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    result = list(dict.fromkeys(to_kebab_case(value) for value in (values or [])))
    if not 1 <= len(result) <= 3:
        raise ValueError("tags must contain between 1 and 3 items")
    if any(not 2 <= len(value) <= 40 for value in result):
        raise ValueError("each tag must contain between 2 and 40 characters")
    return result


def _validate_title(value):
    if not 10 <= len(value) <= 500:
        raise ValueError("title must contain between 10 and 500 characters")



def _validate_content(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100_000:
        raise ValueError("content must contain between 1 and 100000 characters")
    return value.strip()


def _validate_model(slug, version):
    from prompt_models import get_prompt_model
    if not slug and not version:
        return None
    if not slug:
        raise ValueError("model slug must be provided when selecting a model")
    model = get_prompt_model(slug, version)
    if model is None:
        raise ValueError(f"unsupported prompt model: {slug}")
    return model


def _validate_image_filenames(values):
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    values = list(values or [])
    if len(values) > 20:
        raise ValueError("image_filenames must contain at most 20 items")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("image filenames must be non-empty filenames")
    return list(dict.fromkeys(value.strip() for value in values))


def _validate_comment_text(value):
    if not 1 <= len(value) <= 5_000:
        raise ValueError("text must contain between 1 and 5000 characters")


@dataclass(slots=True)
class PromptDTO(BaseDTO):
    title: str
    content: str
    tags: list[str]
    image_filenames: list[str] = field(default_factory=list)
    model_slug: str | None = None
    model_version: str | None = None

    def __post_init__(self):
        _validate_title(self.title)
        self.content = _validate_content(self.content)
        self.tags = _validate_tags(self.tags)
        model = _validate_model(self.model_slug, self.model_version)
        if model and not self.model_version:
            self.model_version = model.version
        self.image_filenames = _validate_image_filenames(self.image_filenames)


@dataclass(slots=True)
class UpdatePromptDTO(BaseDTO):
    title: str | None | object = UNSET
    tags: list[str] | None | object = UNSET
    content: str | object = UNSET
    image_filenames: list[str] | object = UNSET
    model_slug: str | None | object = UNSET
    model_version: str | None | object = UNSET

    def __post_init__(self):
        if self.title is not UNSET:
            if self.title is None:
                raise ValueError("title must contain between 10 and 500 characters")
            _validate_title(self.title)
        if self.tags is not UNSET:
            self.tags = _validate_tags(self.tags)
        if self.content is not UNSET:
            self.content = _validate_content(self.content)
        if self.model_slug is not UNSET or self.model_version is not UNSET:
            _validate_model(
                self.model_slug if self.model_slug is not UNSET else None,
                self.model_version if self.model_version is not UNSET else None,
            )
        if self.image_filenames is not UNSET:
            self.image_filenames = _validate_image_filenames(self.image_filenames)


@dataclass(slots=True)
class UpdateTagDTO(BaseDTO):
    name: str | None | object = UNSET
    image_action: str | None | object = UNSET
    image_filename: str | None | object = UNSET

    def __post_init__(self):
        if self.name is not UNSET:
            if self.name is None or not 2 <= len(self.name) <= 40:
                raise ValueError("name must contain between 2 and 40 characters")
        if self.image_action is not UNSET and self.image_action not in (None, "delete", "replace", "keep"):
            raise ValueError("invalid image action")


@dataclass(slots=True)
class UpdatePromptStatusDTO(BaseDTO):
    status: PromptStatus
    comment: str | None = None

    def __post_init__(self):
        self.status = PromptStatus(self.status)
        if self.status == PromptStatus.REJECTED and not self.comment:
            raise ValueError("Comment is required when rejecting an prompt")


class PromptImpressionAction(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"


@dataclass(slots=True)
class UpdatePromptImpressionDTO(BaseDTO):
    action: PromptImpressionAction

    def __post_init__(self):
        self.action = PromptImpressionAction(self.action)


@dataclass(slots=True)
class PromptCommentDTO(BaseDTO):
    text: str

    def __post_init__(self):
        _validate_comment_text(self.text)


@dataclass(slots=True)
class UpdatePromptCommentDTO(BaseDTO):
    text: str | None | object = UNSET

    def __post_init__(self):
        if self.text is not UNSET:
            if self.text is None:
                raise ValueError("text must contain between 1 and 5000 characters")
            _validate_comment_text(self.text)


class PromptCommentImpressionAction(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"


@dataclass(slots=True)
class UpdatePromptCommentImpressionDTO(BaseDTO):
    action: PromptCommentImpressionAction

    def __post_init__(self):
        self.action = PromptCommentImpressionAction(self.action)
