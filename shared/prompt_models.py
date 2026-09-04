from dataclasses import dataclass
from enum import StrEnum


class PromptCategory(StrEnum):
    DESIGN_IMAGE = "Design & Image"
    SOCIAL_MEDIA = "Social Media"
    WRITING_EDITING = "Writing & Editing"
    DATA_ANALYTICS = "Data & Analytics"
    PHOTOGRAPHY = "Photography"
    MARKETING = "Marketing"
    PRODUCTIVITY = "Productivity"
    EMAIL_OUTREACH = "Email & Outreach"
    CODE_DEV = "Code & Dev"
    BUSINESS_OPS = "Business & Ops"
    EDUCATION = "Education"
    PRODUCT_UX = "Product & UX"
    HR_PEOPLE = "HR & People"
    CREATIVE_WRITING = "Creative Writing"
    RESEARCH_DATA = "Research & Data"
    SALES_CRM = "Sales & CRM"
    CUSTOMER_SUPPORT = "Customer Support"
    SEO_GROWTH = "SEO & Growth"
    ECOMMERCE_RETAIL = "E-commerce & Retail"
    SCIENCE = "Science"
    GAMING = "Gaming"
    MUSIC_AUDIO = "Music & Audio"
    ART_ILLUSTRATION = "Art & Illustration"
    LANGUAGES_TRANSLATION = "Languages & Translation"
    AI_AGENTS_AUTOMATION = "AI Agents & Automation"
    OTHER = "Other"


class PromptOutput(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"


PROMPT_CATEGORIES = tuple(PromptCategory)
PROMPT_OUTPUTS = tuple(PromptOutput)


@dataclass(frozen=True, slots=True)
class PromptModel:
    """A selectable model supported by the catalog."""

    title: str
    slug: str
    version: str


PROMPT_MODELS = (
    PromptModel("GPT-4o", "openai-gpt-4o", "2024-05-13"),
    PromptModel("Claude 3.5 Sonnet", "anthropic-claude-3-5-sonnet", "20241022"),
    PromptModel("Gemini 1.5 Pro", "google-gemini-1-5-pro", "002"),
    PromptModel("Llama 3.1 70B", "meta-llama-3-1-70b", "1.0"),
)


def get_prompt_model(slug: str | None, version: str | None = None) -> PromptModel | None:
    return next((model for model in PROMPT_MODELS if model.slug == slug and (version is None or model.version == version)), None)
