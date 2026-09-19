"""Prompt contracts and canonical persisted records."""
import os
import sys
from enum import StrEnum
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(os.environ.get('PROJECT_ROOT', Path(__file__).resolve().parents[1])) / 'shared'))
from prompt_contracts import extract_template_params, normalize_template_params
from prompt_dtos import PromptDTO, UpdatePromptDTO
from prompt_models import PROMPT_MODELS, PromptModel, get_prompt_model
from shared_utils import prompt_from_dynamodb


def dto(**changes):
    return PromptDTO(**(dict(title='Example', description='Example task', category='code-dev',
                            template={'content': 'Describe {{reference}}', 'format': 'text'},
                            inputs=[{'name': 'reference', 'formats': ['image', 'text']}],
                            outputs=[{'name': 'result', 'formats': ['image', 'audio']}],
                            models=['openai-gpt-4o'], tags=[]) | changes))


def test_single_template_and_named_ports():
    value = dto()
    assert value.template == {'content': 'Describe {{reference}}', 'format': 'text'}
    assert value.inputs == [{'name': 'reference', 'formats': ['image', 'text'], 'required': True}]
    assert dto(inputs=[], outputs=[]).outputs == []
    assert dto(template={'content': '  Preserve whitespace\n', 'format': 'markdown'}).template['content'].startswith('  ')
    assert dto(template={'content': '<!DOCTYPE html><html></html>', 'format': 'html'}).template['format'] == 'html'


def test_category_uses_internal_key():
    assert dto(category='design-image').category == 'design-image'
    with pytest.raises(ValueError):
        dto(category='Design & Image')


def test_model_values_are_canonicalized():
    assert issubclass(PromptModel, StrEnum)
    assert PromptModel.GPT_4O.value == 'openai-gpt-4o'
    assert dto().models == ['openai-gpt-4o']
    assert dto(models=['GPT-4o (2024-05-13)']).models == ['openai-gpt-*']


def test_prompt_can_leave_models_unspecified():
    assert dto(models=[]).models == []


def test_template_params_preserve_names_defaults_and_source_order():
    content = "Use ${Mother Language:Turkish}, ${topic}, then ${mother language}."

    assert extract_template_params(content) == [
        {"name": "mother-language", "default": "Turkish"},
        {"name": "topic"},
    ]
    assert normalize_template_params(content) == (
        "Use ${mother-language:Turkish}, ${topic}, then ${mother-language}."
    )


def test_prompt_limits_fit_upstream_metadata():
    assert len(dto(title='t' * 200, description='d' * 500).title) == 200
    with pytest.raises(ValueError):
        dto(title='t' * 201)
    with pytest.raises(ValueError):
        dto(description='d' * 501)


def test_prompt_models_cover_prompts_chat_models_and_unknown_versions():
    upstream_models = {
        'gpt-5-*', 'nano-banana-pro', 'claude-4-5-opus',
        'gemini-3-pro', 'claude-4-5-sonnet', 'nano-banana',
        'gemini-3', 'gpt-4o', 'grok-4', 'grok-3',
        'claude-4-5-haiku', 'claude-4-opus', 'kling', 'dall-e-3',
        'gemini-2-5-pro', 'claude-3-5-sonnet', 'claude-4-sonnet',
        'veo', 'o4-mini', 'runway-gen4', 'gemini-2-5-flash', 'sora 2',
    }

    assert all(get_prompt_model(model) is not None for model in upstream_models)
    assert get_prompt_model('gpt-*') == PromptModel.GPT_ANY
    assert get_prompt_model('gpt-5-*') == PromptModel.GPT_5_ANY
    assert get_prompt_model('gpt-5-future') == PromptModel.GPT_5_ANY
    assert get_prompt_model('gpt-future') == PromptModel.GPT_ANY
    assert get_prompt_model('gpt-image-future') == PromptModel.GPT_IMAGE_ANY
    assert get_prompt_model('gpt-audio-future') == PromptModel.GPT_AUDIO_ANY
    assert get_prompt_model('claude-*') == PromptModel.CLAUDE_ANY
    assert get_prompt_model('gemini-*') == PromptModel.GEMINI_ANY
    assert get_prompt_model('llama-*') == PromptModel.LLAMA_ANY
    assert len(PROMPT_MODELS) == len(set(PROMPT_MODELS))


def test_prompt_model_aliases_are_stored_as_canonical_slugs():
    assert dto(models=['gpt-5-*', 'claude-4-5-opus', 'sora 2']).models == [
        'openai-gpt-5-*',
        'anthropic-claude-4-5-opus',
        'openai-sora-2',
    ]


def test_optional_text_input_default():
    value = dto(inputs=[{'name': 'language', 'formats': ['text'], 'required': False, 'default': 'English'}])
    assert value.inputs[0]['default'] == 'English'


@pytest.mark.parametrize('changes', [
    {'template': ['Not an object']}, {'template': {}},
    {'template': {'content': '', 'format': 'text'}},
    {'template': {'content': '😀' * 75001, 'format': 'text'}},
    {'template': {'content': 'Example', 'format': 'image'}},
    {'inputs': [{'name': 'source', 'formats': ['unknown']}]},
    {'inputs': [{'name': 'source', 'formats': ['text'], 'required': 'false'}]},
    {'inputs': [{'name': 'source', 'formats': ['text'], 'required': True, 'default': 'value'}]},
    {'inputs': [{'name': 'source', 'formats': ['image'], 'required': False, 'default': 'value'}]},
    {'inputs': [{'name': 'source', 'formats': ['text'], 'required': False, 'default': 'x' * 1001}]},
    {'outputs': ['text']},
    {'outputs': [{'name': 'a', 'formats': []}, {'name': 'a', 'formats': []}]},
    {'outputs': [{'name': 'not a name', 'formats': []}]},
])
def test_invalid_prompt_contract(changes):
    with pytest.raises(ValueError):
        dto(**changes)


def test_partial_update_preserves_unmodified_fields():
    assert UpdatePromptDTO(inputs=[]).get_changes(dto()) == {'inputs': []}
    replacement = {'content': 'New template', 'format': 'text'}
    assert UpdatePromptDTO(template=replacement).get_changes(dto()) == {'template': replacement}


def test_unified_result_files():
    files = [
        {'filename': 'example.png', 'format': 'image'},
        {'filename': 'demo.mp4', 'format': 'video', 'preview_filename': 'demo_320x180.jpg'},
    ]
    assert dto(result_files=files).result_files == files
    assert UpdatePromptDTO(result_files=[]).get_changes(dto(result_files=files)) == {'result_files': []}
    item = dict(id='example', user_id='owner', title='Example', description='Example', category='code-dev',
                prompt_slug='example', status='unpublished', rating_sk=0, created_at=1,
                template={'content': 'Example', 'format': 'text'}, inputs=[], outputs=[],
                result_files=files + [{'filename': 'speech.mp3', 'format': 'audio'}])
    value = prompt_from_dynamodb(item)
    assert value.result_files == files + [{'filename': 'speech.mp3', 'format': 'audio'}]
    assert value.category == 'code-dev'
    assert value.category_label == 'Code & Dev'


def test_old_prompt_records_derive_params_from_template():
    item = dict(id='parameterized', user_id='owner', title='Parameterized', description='Example',
                category='other', prompt_slug='parameterized', status='published', rating_sk=0,
                created_at=1, template={'content': 'Use ${Language:Turkish}.', 'format': 'text'},
                inputs=[], outputs=[])

    value = prompt_from_dynamodb(item)
    assert value.template['content'] == 'Use ${language:Turkish}.'
    assert value.params == [{'name': 'language', 'default': 'Turkish'}]


def test_result_files_are_not_artificially_count_limited():
    files = [{'filename': f'example-{number}.png', 'format': 'image'} for number in range(20)]
    assert dto(result_files=files).result_files == files


@pytest.mark.parametrize('file', [
    {'filename': '../image.png', 'format': 'image'},
    {'filename': 'https://example.com/demo.mp4', 'format': 'video'},
    {'filename': 'javascript:alert(1)', 'format': 'image'},
    {'filename': 'file.html', 'format': 'html'},
    {'filename': 'speech.mp3', 'format': 'audio', 'preview_filename': 'preview.jpg'},
    {'filename': 'demo.mp4', 'format': 'video', 'preview_filename': '../preview.jpg'},
    {'filename': 'demo.mp4', 'format': 'video', 'unknown': 'value'},
])
def test_invalid_result_files(file):
    with pytest.raises(ValueError):
        dto(result_files=[file])


def test_image_url_result():
    file = {'filename': 'https://example.com/image.png', 'format': 'image'}
    assert dto(result_files=[file, file]).result_files == [file]
