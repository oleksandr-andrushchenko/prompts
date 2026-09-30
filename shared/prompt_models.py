from enum import StrEnum


class PromptFormat(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    HTML = "html"
    XML = "xml"
    CSV = "csv"
    CODE = "code"


PROMPT_FORMATS = tuple(PromptFormat)
PROMPT_TEMPLATE_FORMATS = tuple(value for value in PromptFormat if value not in (
    PromptFormat.IMAGE, PromptFormat.VIDEO, PromptFormat.AUDIO, PromptFormat.DOCUMENT,
))


class PromptModel(StrEnum):
    GPT_ANY = "openai-gpt-*"
    GPT_5_ANY = "openai-gpt-5-*"
    GPT_4O = "openai-gpt-4o"
    O4_MINI = "openai-o4-mini"
    DALL_E_ANY = "openai-dall-e-*"
    DALL_E_3 = "openai-dall-e-3"
    GPT_IMAGE_ANY = "openai-gpt-image-*"
    GPT_IMAGE_2_5_SUNBURST = "openai-gpt-image-2-5-sunburst"
    GPT_IMAGE_2_5_FLARE = "openai-gpt-image-2-5-flare"
    SORA_ANY = "openai-sora-*"
    SORA_2 = "openai-sora-2"
    SORA_2_PRO = "openai-sora-2-pro"
    GPT_AUDIO_ANY = "openai-gpt-audio-*"
    GPT_REALTIME_ANY = "openai-gpt-realtime-*"
    GPT_TRANSCRIBE_ANY = "openai-gpt-transcribe-*"
    GPT_4O_MINI_TTS = "openai-gpt-4o-mini-tts"
    TTS_ANY = "openai-tts-*"
    TTS_1 = "openai-tts-1"
    TTS_1_HD = "openai-tts-1-hd"
    WHISPER_ANY = "openai-whisper-*"
    WHISPER_1 = "openai-whisper-1"

    CLAUDE_ANY = "anthropic-claude-*"
    CLAUDE_3_5_SONNET = "anthropic-claude-3-5-sonnet"
    CLAUDE_4_SONNET = "anthropic-claude-4-sonnet"
    CLAUDE_4_OPUS = "anthropic-claude-4-opus"
    CLAUDE_4_5_HAIKU = "anthropic-claude-4-5-haiku"
    CLAUDE_4_5_SONNET = "anthropic-claude-4-5-sonnet"
    CLAUDE_4_5_OPUS = "anthropic-claude-4-5-opus"

    GEMINI_ANY = "google-gemini-*"
    GEMINI_1_5_PRO = "google-gemini-1-5-pro"
    GEMINI_2_5_FLASH = "google-gemini-2-5-flash"
    GEMINI_2_5_PRO = "google-gemini-2-5-pro"
    GEMINI_3 = "google-gemini-3"
    GEMINI_3_PRO = "google-gemini-3-pro"
    NANO_BANANA_ANY = "google-nano-banana-*"
    NANO_BANANA = "google-nano-banana"
    NANO_BANANA_PRO = "google-nano-banana-pro"
    IMAGEN_ANY = "google-imagen-*"
    VEO_ANY = "google-veo-*"
    VEO = "google-veo"

    GROK_ANY = "xai-grok-*"
    GROK_3 = "xai-grok-3"
    GROK_4 = "xai-grok-4"

    LLAMA_ANY = "meta-llama-*"
    LLAMA_3_1_70B = "meta-llama-3-1-70b"
    DEEPSEEK_ANY = "deepseek-*"
    QWEN_ANY = "alibaba-qwen-*"
    MISTRAL_ANY = "mistral-*"
    COMMAND_ANY = "cohere-command-*"
    SONAR_ANY = "perplexity-sonar-*"

    KLING_ANY = "kling-*"
    KLING = "kling"
    RUNWAY_ANY = "runway-*"
    RUNWAY_GEN4 = "runway-gen4"
    MIDJOURNEY_ANY = "midjourney-*"
    MIDJOURNEY = "midjourney"
    FLUX_ANY = "black-forest-labs-flux-*"
    STABLE_DIFFUSION_ANY = "stability-ai-stable-diffusion-*"
    IDEOGRAM_ANY = "ideogram-*"
    RECRAFT_ANY = "recraft-*"
    FIREFLY_ANY = "adobe-firefly-*"
    SEEDANCE_ANY = "bytedance-seedance-*"
    SEEDANCE_2_0 = "bytedance-seedance-2-0"
    SEEDANCE_2_5 = "bytedance-seedance-2-5"
    LUMA_RAY_ANY = "luma-ray-*"
    PIKA_ANY = "pika-*"
    HAILUO_ANY = "minimax-hailuo-*"
    WAN_ANY = "alibaba-wan-*"

    ELEVENLABS_ANY = "elevenlabs-*"
    SUNO_ANY = "suno-*"
    UDIO_ANY = "udio-*"


PROMPT_MODELS = tuple(PromptModel)


# Normalize common unqualified model spellings into the catalog's stable
# provider-qualified model slugs.
PROMPT_MODEL_ALIASES = {
    "gpt-*": PromptModel.GPT_ANY,
    "gpt-5-*": PromptModel.GPT_5_ANY,
    "gpt-4o": PromptModel.GPT_4O,
    "o4-mini": PromptModel.O4_MINI,
    "dall-e-*": PromptModel.DALL_E_ANY,
    "dall-e-3": PromptModel.DALL_E_3,
    "gpt-image-*": PromptModel.GPT_IMAGE_ANY,
    "gpt-image-2.5-sunburst": PromptModel.GPT_IMAGE_2_5_SUNBURST,
    "gpt-image-2.5-flare": PromptModel.GPT_IMAGE_2_5_FLARE,
    "sora-*": PromptModel.SORA_ANY,
    "sora 2": PromptModel.SORA_2,
    "sora 2 pro": PromptModel.SORA_2_PRO,
    "gpt-audio-*": PromptModel.GPT_AUDIO_ANY,
    "gpt-realtime-*": PromptModel.GPT_REALTIME_ANY,
    "gpt-transcribe-*": PromptModel.GPT_TRANSCRIBE_ANY,
    "gpt-4o-mini-tts": PromptModel.GPT_4O_MINI_TTS,
    "tts-*": PromptModel.TTS_ANY,
    "tts-1": PromptModel.TTS_1,
    "tts-1-hd": PromptModel.TTS_1_HD,
    "whisper-*": PromptModel.WHISPER_ANY,
    "whisper-1": PromptModel.WHISPER_1,
    "claude-*": PromptModel.CLAUDE_ANY,
    "claude-3-5-sonnet": PromptModel.CLAUDE_3_5_SONNET,
    "claude-4-sonnet": PromptModel.CLAUDE_4_SONNET,
    "claude-4-opus": PromptModel.CLAUDE_4_OPUS,
    "claude-4-5-haiku": PromptModel.CLAUDE_4_5_HAIKU,
    "claude-4-5-sonnet": PromptModel.CLAUDE_4_5_SONNET,
    "claude-4-5-opus": PromptModel.CLAUDE_4_5_OPUS,
    "gemini-*": PromptModel.GEMINI_ANY,
    "gemini-1-5-pro": PromptModel.GEMINI_1_5_PRO,
    "gemini-2-5-flash": PromptModel.GEMINI_2_5_FLASH,
    "gemini-2-5-pro": PromptModel.GEMINI_2_5_PRO,
    "gemini-3": PromptModel.GEMINI_3,
    "gemini-3-pro": PromptModel.GEMINI_3_PRO,
    "nano-banana-*": PromptModel.NANO_BANANA_ANY,
    "nano-banana": PromptModel.NANO_BANANA,
    "nano-banana-pro": PromptModel.NANO_BANANA_PRO,
    "imagen-*": PromptModel.IMAGEN_ANY,
    "veo-*": PromptModel.VEO_ANY,
    "veo": PromptModel.VEO,
    "grok-*": PromptModel.GROK_ANY,
    "grok-3": PromptModel.GROK_3,
    "grok-4": PromptModel.GROK_4,
    "llama-*": PromptModel.LLAMA_ANY,
    "llama-3-1-70b": PromptModel.LLAMA_3_1_70B,
    "deepseek": PromptModel.DEEPSEEK_ANY,
    "deepseek-*": PromptModel.DEEPSEEK_ANY,
    "qwen": PromptModel.QWEN_ANY,
    "qwen-*": PromptModel.QWEN_ANY,
    "mistral": PromptModel.MISTRAL_ANY,
    "mistral-*": PromptModel.MISTRAL_ANY,
    "command": PromptModel.COMMAND_ANY,
    "command-*": PromptModel.COMMAND_ANY,
    "command-r": PromptModel.COMMAND_ANY,
    "command-r-plus": PromptModel.COMMAND_ANY,
    "sonar": PromptModel.SONAR_ANY,
    "sonar-*": PromptModel.SONAR_ANY,
    "kling-*": PromptModel.KLING_ANY,
    "kling": PromptModel.KLING,
    "runway-*": PromptModel.RUNWAY_ANY,
    "runway-gen4": PromptModel.RUNWAY_GEN4,
    "midjourney-*": PromptModel.MIDJOURNEY_ANY,
    "midjourney": PromptModel.MIDJOURNEY,
    "flux": PromptModel.FLUX_ANY,
    "flux-*": PromptModel.FLUX_ANY,
    "stable diffusion": PromptModel.STABLE_DIFFUSION_ANY,
    "stable-diffusion-*": PromptModel.STABLE_DIFFUSION_ANY,
    "ideogram": PromptModel.IDEOGRAM_ANY,
    "ideogram-*": PromptModel.IDEOGRAM_ANY,
    "recraft": PromptModel.RECRAFT_ANY,
    "recraft-*": PromptModel.RECRAFT_ANY,
    "firefly": PromptModel.FIREFLY_ANY,
    "firefly-*": PromptModel.FIREFLY_ANY,
    "adobe firefly": PromptModel.FIREFLY_ANY,
    "seedance-*": PromptModel.SEEDANCE_ANY,
    "seedance 2.0": PromptModel.SEEDANCE_2_0,
    "seedance2.0": PromptModel.SEEDANCE_2_0,
    "seedance-2.0": PromptModel.SEEDANCE_2_0,
    "seedance-2-0": PromptModel.SEEDANCE_2_0,
    "seedance 2.5": PromptModel.SEEDANCE_2_5,
    "seedance2.5": PromptModel.SEEDANCE_2_5,
    "seedance-2.5": PromptModel.SEEDANCE_2_5,
    "seedance-2-5": PromptModel.SEEDANCE_2_5,
    "luma ray": PromptModel.LUMA_RAY_ANY,
    "luma-ray-*": PromptModel.LUMA_RAY_ANY,
    "pika": PromptModel.PIKA_ANY,
    "pika-*": PromptModel.PIKA_ANY,
    "hailuo": PromptModel.HAILUO_ANY,
    "hailuo-*": PromptModel.HAILUO_ANY,
    "wan": PromptModel.WAN_ANY,
    "wan-*": PromptModel.WAN_ANY,
    "elevenlabs-*": PromptModel.ELEVENLABS_ANY,
    "suno-*": PromptModel.SUNO_ANY,
    "udio": PromptModel.UDIO_ANY,
    "udio-*": PromptModel.UDIO_ANY,
}


PROMPT_MODEL_PREFIX_ALIASES = (
    ("openai-gpt-5-", PromptModel.GPT_5_ANY),
    ("gpt-5-", PromptModel.GPT_5_ANY),
    ("openai-gpt-image-", PromptModel.GPT_IMAGE_ANY),
    ("gpt-image-", PromptModel.GPT_IMAGE_ANY),
    ("openai-gpt-audio-", PromptModel.GPT_AUDIO_ANY),
    ("gpt-audio-", PromptModel.GPT_AUDIO_ANY),
    ("openai-gpt-realtime-", PromptModel.GPT_REALTIME_ANY),
    ("gpt-realtime-", PromptModel.GPT_REALTIME_ANY),
    ("openai-gpt-transcribe-", PromptModel.GPT_TRANSCRIBE_ANY),
    ("gpt-transcribe-", PromptModel.GPT_TRANSCRIBE_ANY),
    ("openai-gpt-", PromptModel.GPT_ANY),
    ("gpt-", PromptModel.GPT_ANY),
    ("openai-dall-e-", PromptModel.DALL_E_ANY),
    ("dall-e-", PromptModel.DALL_E_ANY),
    ("openai-sora-", PromptModel.SORA_ANY),
    ("sora-", PromptModel.SORA_ANY),
    ("anthropic-claude-", PromptModel.CLAUDE_ANY),
    ("claude-", PromptModel.CLAUDE_ANY),
    ("google-gemini-", PromptModel.GEMINI_ANY),
    ("gemini-", PromptModel.GEMINI_ANY),
    ("google-nano-banana-", PromptModel.NANO_BANANA_ANY),
    ("nano-banana-", PromptModel.NANO_BANANA_ANY),
    ("google-imagen-", PromptModel.IMAGEN_ANY),
    ("imagen-", PromptModel.IMAGEN_ANY),
    ("google-veo-", PromptModel.VEO_ANY),
    ("veo-", PromptModel.VEO_ANY),
    ("xai-grok-", PromptModel.GROK_ANY),
    ("grok-", PromptModel.GROK_ANY),
    ("meta-llama-", PromptModel.LLAMA_ANY),
    ("llama-", PromptModel.LLAMA_ANY),
    ("deepseek-", PromptModel.DEEPSEEK_ANY),
    ("deepseek ", PromptModel.DEEPSEEK_ANY),
    ("alibaba-qwen-", PromptModel.QWEN_ANY),
    ("qwen-", PromptModel.QWEN_ANY),
    ("qwen ", PromptModel.QWEN_ANY),
    ("mistral-", PromptModel.MISTRAL_ANY),
    ("mistral ", PromptModel.MISTRAL_ANY),
    ("cohere-command-", PromptModel.COMMAND_ANY),
    ("command-", PromptModel.COMMAND_ANY),
    ("command ", PromptModel.COMMAND_ANY),
    ("perplexity-sonar-", PromptModel.SONAR_ANY),
    ("sonar-", PromptModel.SONAR_ANY),
    ("sonar ", PromptModel.SONAR_ANY),
    ("kling-", PromptModel.KLING_ANY),
    ("runway-", PromptModel.RUNWAY_ANY),
    ("midjourney-", PromptModel.MIDJOURNEY_ANY),
    ("midjourney ", PromptModel.MIDJOURNEY_ANY),
    ("black-forest-labs-flux-", PromptModel.FLUX_ANY),
    ("flux-", PromptModel.FLUX_ANY),
    ("flux ", PromptModel.FLUX_ANY),
    ("stability-ai-stable-diffusion-", PromptModel.STABLE_DIFFUSION_ANY),
    ("stable-diffusion-", PromptModel.STABLE_DIFFUSION_ANY),
    ("stable diffusion ", PromptModel.STABLE_DIFFUSION_ANY),
    ("ideogram-", PromptModel.IDEOGRAM_ANY),
    ("ideogram ", PromptModel.IDEOGRAM_ANY),
    ("recraft-", PromptModel.RECRAFT_ANY),
    ("recraft ", PromptModel.RECRAFT_ANY),
    ("adobe-firefly-", PromptModel.FIREFLY_ANY),
    ("adobe firefly ", PromptModel.FIREFLY_ANY),
    ("firefly-", PromptModel.FIREFLY_ANY),
    ("bytedance-seedance-", PromptModel.SEEDANCE_ANY),
    ("seedance-", PromptModel.SEEDANCE_ANY),
    ("luma-ray-", PromptModel.LUMA_RAY_ANY),
    ("luma ray ", PromptModel.LUMA_RAY_ANY),
    ("pika-", PromptModel.PIKA_ANY),
    ("pika ", PromptModel.PIKA_ANY),
    ("minimax-hailuo-", PromptModel.HAILUO_ANY),
    ("hailuo-", PromptModel.HAILUO_ANY),
    ("hailuo ", PromptModel.HAILUO_ANY),
    ("alibaba-wan-", PromptModel.WAN_ANY),
    ("wan-", PromptModel.WAN_ANY),
    ("wan ", PromptModel.WAN_ANY),
    ("elevenlabs-", PromptModel.ELEVENLABS_ANY),
    ("suno-", PromptModel.SUNO_ANY),
    ("udio-", PromptModel.UDIO_ANY),
    ("udio ", PromptModel.UDIO_ANY),
)


def get_prompt_model(value: str | None) -> PromptModel | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    try:
        return PromptModel(value)
    except ValueError:
        return PROMPT_MODEL_ALIASES.get(value) or next(
            (model for prefix, model in PROMPT_MODEL_PREFIX_ALIASES if value.startswith(prefix)), None
        )
