from http import HTTPStatus
from typing import Annotated

from starlette.responses import HTMLResponse

from query_dtos import PromptQueryDTO, UserQueryDTO
from shared_deps import OptCurUserDep
from shared_utils import Prompt, PromptNotFoundError, User, UserNotFoundError, get_html_content
from web import Depends, HTTPException, Request, parse_dto
from web_utils import get_prompt_by_slugs, get_user_by_slug, parse_prompts_url_slugs_path


def get_error_response(status_code: int, details: dict | str = None):
    status_enum = HTTPStatus(status_code)
    public_data = {
        "code": status_code,
        "title": status_enum.phrase,
        "message": status_enum.description,
        "details": details,
    }
    content = get_html_content("error.html", public_data)
    return HTMLResponse(status_code=status_code, content=content)


def get_user_query_by_slugs(request: Request, type: str) -> UserQueryDTO:
    data = dict(request.query_params)
    data.update({"type": type})
    return parse_dto(UserQueryDTO, data)


def get_prompt_query_by_slugs(request: Request, slugs_path: str) -> PromptQueryDTO:
    data = dict(request.query_params)
    data.update(parse_prompts_url_slugs_path(slugs_path))
    return parse_dto(PromptQueryDTO, data)


def _get_user_by_slug(slug: str, cur_user: OptCurUserDep = None) -> User:
    try:
        return get_user_by_slug(slug, cur_user)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _get_prompt_by_slugs(user_slug: str, prompt_slug: str, cur_user: OptCurUserDep = None) -> Prompt:
    try:
        return get_prompt_by_slugs(user_slug, prompt_slug, cur_user)
    except PromptNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


UserBySlugDep = Annotated[User, Depends(_get_user_by_slug)]
UserQueryBySlugsDep = Annotated[UserQueryDTO, Depends(get_user_query_by_slugs)]
PromptBySlugsDep = Annotated[Prompt, Depends(_get_prompt_by_slugs)]
PromptQueryBySlugsDep = Annotated[PromptQueryDTO, Depends(get_prompt_query_by_slugs)]
