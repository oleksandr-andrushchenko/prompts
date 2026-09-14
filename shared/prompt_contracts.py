"""Reusable template and named input/output contracts."""
import re

from prompt_models import PROMPT_FORMATS, PROMPT_TEMPLATE_FORMATS


TEMPLATE_PARAM_RE = re.compile(r'\$\{\s*([^}:\r\n]+?)\s*(?::([^}\r\n]*))?\s*\}')


def normalize_template_param_name(value):
    return re.sub(r'[_\W]+', '-', value.casefold().strip()).strip('-')


def normalize_template_params(content):
    """Canonicalize parameter names while retaining `${name:default}` syntax."""
    if not isinstance(content, str):
        return content

    def replace(match):
        name = normalize_template_param_name(match.group(1))
        if not name:
            return match.group(0)
        default = match.group(2)
        return '${' + name + (':' + default.strip() if default is not None else '') + '}'

    return TEMPLATE_PARAM_RE.sub(replace, content)


def extract_template_params(content):
    """Return unique parameters in source order without rewriting the template."""
    if not isinstance(content, str):
        return []
    params = []
    indexes = {}
    for match in TEMPLATE_PARAM_RE.finditer(content):
        name = normalize_template_param_name(match.group(1))
        if not name:
            continue
        key = name.casefold()
        default = match.group(2)
        item = {'name': name}
        if default is not None:
            item['default'] = default.strip()
        if key not in indexes:
            indexes[key] = len(params)
            params.append(item)
        elif 'default' not in params[indexes[key]] and 'default' in item:
            params[indexes[key]]['default'] = item['default']
    return params


def validate_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value):
        raise ValueError('name must start with a letter or underscore and contain up to 64 letters, digits or underscores')
    return value


def validate_template(value):
    if not isinstance(value, dict) or set(value) != {'content', 'format'}:
        raise ValueError('template requires content and format')
    content = value['content']
    if not isinstance(content, str) or not content.strip():
        raise ValueError('template content must be non-empty text')
    if len(content.encode('utf-8')) > 300_000:
        raise ValueError('template content must not exceed 300000 UTF-8 bytes')
    if value['format'] not in PROMPT_TEMPLATE_FORMATS:
        raise ValueError('template format must be a supported textual format')
    return dict(content=normalize_template_params(content), format=value['format'])


def validate_ports(values, *, inputs=False):
    try:
        return _validate_ports(values, inputs=inputs)
    except ValueError as exc:
        raise ValueError(f"{'inputs' if inputs else 'outputs'} {exc}") from exc


def _validate_ports(values, *, inputs=False):
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError('inputs/outputs must be a list of at most 64 named declarations')
    result, names = [], set()
    for value in values:
        allowed = {'name', 'formats', 'description'} | ({'required', 'default'} if inputs else set())
        if not isinstance(value, dict) or set(value) - allowed or not {'name', 'formats'} <= set(value):
            raise ValueError('inputs/outputs require name and formats; optional description and input required flag')
        name = validate_name(value['name'])
        if name in names:
            raise ValueError(f'inputs/outputs contain duplicate name: {name}')
        names.add(name)
        formats = value['formats']
        if (not isinstance(formats, list) or any(not isinstance(fmt, str) or fmt not in PROMPT_FORMATS for fmt in formats)):
            raise ValueError('formats must be a list of supported formats')
        item = dict(name=name, formats=list(dict.fromkeys(formats)))
        if inputs:
            required = value.get('required', True)
            if not isinstance(required, bool):
                raise ValueError('required must be a boolean')
            item['required'] = required
            if 'default' in value:
                default = value['default']
                if not isinstance(default, str) or len(default.encode('utf-8')) > 1_000:
                    raise ValueError('default must be text of at most 1000 UTF-8 bytes')
                if required:
                    raise ValueError('an input with a default must not be required')
                if 'text' not in formats:
                    raise ValueError('default is supported only for text inputs')
                item['default'] = default
        if 'description' in value:
            if not isinstance(value['description'], str) or len(value['description']) > 400:
                raise ValueError('description must be text of at most 400 characters')
            item['description'] = value['description']
        result.append(item)
    return result
