from dataclasses import asdict, dataclass, field
from enum import StrEnum

from prompt_models import normalize_model_slug
from validation import validate_category_slug


@dataclass(slots=True)
class BaseQueryDTO:
    DEFAULT_OFFSET = None
    DEFAULT_LIMIT = 40

    offset: str | None = DEFAULT_OFFSET
    limit: int = DEFAULT_LIMIT

    def __post_init__(self):
        self.limit = _limit(self.limit)

    def get_dict(self, rewrite=None):
        result = asdict(self)
        result.update(rewrite or {})
        return {k: v.value if isinstance(v, StrEnum) else v for k, v in result.items()}

    def has_params(self):
        return self.offset is not None or self.limit != self.DEFAULT_LIMIT


def _limit(value) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if not 1 <= value <= BaseQueryDTO.DEFAULT_LIMIT and value != 1000:
        raise ValueError("limit must be between 1 and " + str(BaseQueryDTO.DEFAULT_LIMIT))
    return value


class UserQueryType(StrEnum):
    LATEST = "latest"
    POPULAR = "popular"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BANNED = "banned"


@dataclass(slots=True)
class UserQueryDTO(BaseQueryDTO):
    DEFAULT_TYPE = UserQueryType.LATEST
    DEFAULT_STATUS = UserStatus.ACTIVE

    type: UserQueryType = UserQueryType.LATEST
    status: UserStatus = UserStatus.ACTIVE

    def __post_init__(self):
        BaseQueryDTO.__post_init__(self)
        self.type = UserQueryType(self.type)
        self.status = UserStatus(self.status)

    def has_params(self):
        return BaseQueryDTO.has_params(self) or self.type != self.DEFAULT_TYPE or self.status != self.DEFAULT_STATUS


class TagQueryType(StrEnum):
    LATEST = "latest"
    POPULAR = "popular"


@dataclass(slots=True)
class TagQueryDTO(BaseQueryDTO):
    DEFAULT_TYPE = TagQueryType.LATEST

    type: TagQueryType = DEFAULT_TYPE
    prefix: str | None = None

    def __post_init__(self):
        BaseQueryDTO.__post_init__(self)
        self.type = TagQueryType(self.type)
        if self.prefix is not None and not 1 <= len(self.prefix) <= 40:
            raise ValueError("prefix must contain between 1 and 40 characters")

    def has_params(self):
        return BaseQueryDTO.has_params(self) or self.type != self.DEFAULT_TYPE or self.prefix is not None


@dataclass(slots=True)
class ModelQueryDTO(BaseQueryDTO):
    prefix: str | None = None

    def __post_init__(self):
        BaseQueryDTO.__post_init__(self)
        if self.prefix is not None and not 1 <= len(self.prefix) <= 100:
            raise ValueError("prefix must contain between 1 and 100 characters")

    def has_params(self):
        return BaseQueryDTO.has_params(self) or self.prefix is not None


class PromptQueryType(StrEnum):
    LATEST = "latest"
    POPULAR = "popular"


class PromptStatus(StrEnum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    REJECTED = "rejected"


@dataclass(slots=True)
class PromptQueryDTO(BaseQueryDTO):
    DEFAULT_TYPE = PromptQueryType.LATEST
    DEFAULT_STATUS = PromptStatus.PUBLISHED

    tags: list[str] = field(default_factory=list)
    category: str | None = None
    model: str | None = None
    type: PromptQueryType = PromptQueryType.LATEST
    status: PromptStatus = PromptStatus.PUBLISHED

    def __post_init__(self):
        BaseQueryDTO.__post_init__(self)
        self.type = PromptQueryType(self.type)
        self.status = PromptStatus(self.status)
        self.tags = sorted({tag for tag in self.tags if tag})
        if self.category == "":
            self.category = None
        if self.model == "":
            self.model = None
        if self.category is not None:
            self.category = validate_category_slug(self.category)
        if self.model is not None:
            self.model = normalize_model_slug(self.model)
            if not self.model or not 2 <= len(self.model) <= 100:
                raise ValueError("model must contain between 2 and 100 characters")

    def has_params(self):
        return BaseQueryDTO.has_params(self) or bool(
            self.tags) or self.category is not None or self.model is not None \
            or self.type != self.DEFAULT_TYPE or self.status != self.DEFAULT_STATUS


@dataclass(slots=True)
class PromptCommentQueryDTO(BaseQueryDTO):
    pass
