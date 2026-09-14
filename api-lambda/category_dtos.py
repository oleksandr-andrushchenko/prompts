from dataclasses import dataclass

from basic_dtos import BaseDTO, UNSET


@dataclass(slots=True)
class UpdateCategoryDTO(BaseDTO):
    description: str | object = UNSET
    image_action: str | object = UNSET
    image_filename: str | None | object = UNSET

    def __post_init__(self):
        if self.description is not UNSET:
            self.description = self.description.strip()
            if not 10 <= len(self.description) <= 500:
                raise ValueError("description must contain between 10 and 500 characters")
        if self.image_action is not UNSET and self.image_action not in {"delete", "replace", "keep"}:
            raise ValueError("invalid image action")
