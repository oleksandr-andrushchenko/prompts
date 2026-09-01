from dataclasses import dataclass


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
