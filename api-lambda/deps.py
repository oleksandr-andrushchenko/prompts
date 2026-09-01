"""API-only request dependencies.

The web lambda keeps the shared read/query dependencies in ``shared``;
upload and mutation request parsing belongs to the API lambda.
"""

from shared_deps import *
from prompt_dtos import UpdatePromptCommentDTO, UpdatePromptCommentImpressionDTO, UpdatePromptDTO, UpdatePromptImpressionDTO, UpdatePromptStatusDTO, UpdateTagDTO
from tag_subscription_dtos import TagSubscriptionDTO
from basic_dtos import ImageFileDTO
from query_dtos import TagQueryDTO
from user_dtos import UpdateUserDTO, UpdateUserActivitySettingsDTO, UpdateUserImpressionDTO, UpdateUserInterestsSettingsDTO, UpdateUserStatusDTO
from shared_utils import PromptComment, PromptCommentNotFoundError, get_prompt_comment
from web import Body, HTTPException, Request


async def get_image_file(request: Request):
    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(status_code=422, detail="Missing file")
    try:
        return ImageFileDTO(content=await file.read(), filename=file.filename)
    except ValueError as exc:
        raise RequestValidationError({"file": str(exc)}) from exc


def get_update_user_dto(value: UpdateUserDTO = Body(...)) -> UpdateUserDTO:
    return value


def get_tag_subscription_dto(value: TagSubscriptionDTO = Body(...)) -> TagSubscriptionDTO:
    return value


def get_update_user_activity_settings_dto(
        value: UpdateUserActivitySettingsDTO = Body(...)) -> UpdateUserActivitySettingsDTO:
    return value


def get_update_user_interests_settings_dto(
        value: UpdateUserInterestsSettingsDTO = Body(...)) -> UpdateUserInterestsSettingsDTO:
    return value


def get_update_user_status_dto(value: UpdateUserStatusDTO = Body(...)) -> UpdateUserStatusDTO:
    return value


def get_update_prompt_dto(value: UpdatePromptDTO = Body(...)) -> UpdatePromptDTO:
    return value


def get_update_prompt_status_dto(value: UpdatePromptStatusDTO = Body(...)) -> UpdatePromptStatusDTO:
    return value


def get_update_prompt_impression_dto(value: UpdatePromptImpressionDTO = Body(...)) -> UpdatePromptImpressionDTO:
    return value


def get_prompt_comment_by_id(prompt_id: str, comment_id: str) -> PromptComment:
    try:
        return get_prompt_comment(prompt_id, comment_id)
    except PromptCommentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def get_update_prompt_comment_dto(value: UpdatePromptCommentDTO = Body(...)) -> UpdatePromptCommentDTO:
    return value


def get_update_prompt_comment_impression_dto(
        value: UpdatePromptCommentImpressionDTO = Body(...)) -> UpdatePromptCommentImpressionDTO:
    return value


def get_update_user_impression_dto(value: UpdateUserImpressionDTO = Body(...)) -> UpdateUserImpressionDTO:
    return value


def get_update_tag_dto(value: UpdateTagDTO = Body(...)) -> UpdateTagDTO:
    return value


UpdateUserDTODep = Annotated[UpdateUserDTO, Depends(get_update_user_dto)]
UpdateUserActivitySettingsDTODep = Annotated[
    UpdateUserActivitySettingsDTO, Depends(get_update_user_activity_settings_dto)]
UpdateUserInterestsSettingsDTODep = Annotated[
    UpdateUserInterestsSettingsDTO, Depends(get_update_user_interests_settings_dto)]
UpdateUserStatusDTODep = Annotated[UpdateUserStatusDTO, Depends(get_update_user_status_dto)]
UpdatePromptDTODep = Annotated[UpdatePromptDTO, Depends(get_update_prompt_dto)]
UpdatePromptStatusDTODep = Annotated[UpdatePromptStatusDTO, Depends(get_update_prompt_status_dto)]
UpdatePromptImpressionDTODep = Annotated[UpdatePromptImpressionDTO, Depends(get_update_prompt_impression_dto)]
PromptCommentDep = Annotated[PromptComment, Depends(get_prompt_comment_by_id)]
UpdatePromptCommentDTODep = Annotated[UpdatePromptCommentDTO, Depends(get_update_prompt_comment_dto)]
UpdatePromptCommentImpressionDTODep = Annotated[
    UpdatePromptCommentImpressionDTO, Depends(get_update_prompt_comment_impression_dto)]
TagQueryDep = Annotated[TagQueryDTO, Depends()]
TagDep = Annotated[Tag, Depends(get_tag_by_slug)]
UpdateTagDTODep = Annotated[UpdateTagDTO, Depends(get_update_tag_dto)]
TagSubscriptionDTODep = Annotated[TagSubscriptionDTO, Depends(get_tag_subscription_dto)]
ImageFileDTODep = Annotated[ImageFileDTO, Depends(get_image_file)]
UpdateUserImpressionDTODep = Annotated[UpdateUserImpressionDTO, Depends(get_update_user_impression_dto)]
