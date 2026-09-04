from dataclasses import dataclass, field
from enum import StrEnum

from basic_dtos import BaseDTO, UNSET
from prompt_models import PromptCategory, PromptOutput
from query_dtos import PromptStatus


def _validate_tags(values):
    from shared_utils import to_kebab_case
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    result = list(dict.fromkeys(to_kebab_case(value) for value in (values or [])))
    if len(result) > 3:
        raise ValueError("tags must contain at most 3 items")
    if any(not 2 <= len(value) <= 40 for value in result):
        raise ValueError("each tag must contain between 2 and 40 characters")
    return result


def _validate_title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 140:
        raise ValueError("title must contain between 1 and 140 characters")
    return value.strip()


def _validate_description(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 400:
        raise ValueError("description must contain between 1 and 400 characters")
    return value.strip()


def _validate_category(value):
    try:
        return PromptCategory(value).value
    except (TypeError, ValueError):
        raise ValueError(f"unsupported prompt category: {value}") from None


def _validate_outputs(values):
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    result = list(dict.fromkeys(values or []))
    try:
        result = [PromptOutput(value).value for value in result]
    except (TypeError, ValueError):
        raise ValueError("outputs must contain only text, image, or video") from None
    if not result:
        raise ValueError("outputs must contain at least one output type")
    return result



def _validate_template(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100_000:
        raise ValueError("template must contain between 1 and 100000 characters")
    return value.strip()


def _validate_models(values):
    from prompt_models import get_prompt_model
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    result = list(dict.fromkeys(values or []))
    if not result:
        raise ValueError("at least one model is required")
    models = []
    for value in result:
        model = get_prompt_model(value)
        if model is None:
            raise ValueError(f"unsupported prompt model: {value}")
        models.append(model.slug)
    return models


def _validate_image_filenames(values):
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",") if value.strip()]
    values = list(values or [])
    if len(values) > 8:
        raise ValueError("image_filenames must contain at most 8 items")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("image filenames must be non-empty filenames")
    return list(dict.fromkeys(value.strip() for value in values))


def _validate_comment_text(value):
    if not 1 <= len(value) <= 5_000:
        raise ValueError("text must contain between 1 and 5000 characters")


@dataclass(slots=True)
class PromptDTO(BaseDTO):
    title: str
    description: str
    category: str
    outputs: list[str]
    template: str
    tags: list[str]
    models: list[str]
    image_filenames: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.title = _validate_title(self.title)
        self.description = _validate_description(self.description)
        self.category = _validate_category(self.category)
        self.outputs = _validate_outputs(self.outputs)
        self.template = _validate_template(self.template)
        self.tags = _validate_tags(self.tags)
        self.models = _validate_models(self.models)
        self.image_filenames = _validate_image_filenames(self.image_filenames)


@dataclass(slots=True)
class UpdatePromptDTO(BaseDTO):
    title: str | None | object = UNSET
    description: str | None | object = UNSET
    category: str | None | object = UNSET
    outputs: list[str] | object = UNSET
    tags: list[str] | None | object = UNSET
    template: str | object = UNSET
    image_filenames: list[str] | object = UNSET
    models: list[str] | object = UNSET

    def __post_init__(self):
        if self.title is not UNSET:
            if self.title is None:
                raise ValueError("title must contain between 1 and 140 characters")
            self.title = _validate_title(self.title)
        if self.description is not UNSET:
            if self.description is None:
                raise ValueError("description must contain between 1 and 400 characters")
            self.description = _validate_description(self.description)
        if self.category is not UNSET:
            if self.category is None:
                raise ValueError("category is required")
            self.category = _validate_category(self.category)
        if self.outputs is not UNSET:
            self.outputs = _validate_outputs(self.outputs)
        if self.tags is not UNSET:
            self.tags = _validate_tags(self.tags)
        if self.template is not UNSET:
            self.template = _validate_template(self.template)
        if self.models is not UNSET:
            self.models = _validate_models(self.models)
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
