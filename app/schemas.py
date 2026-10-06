from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

MAX_ITEMS = 1000
MAX_STRING_LENGTH = 1000

Item = Annotated[str, StringConstraints(max_length=MAX_STRING_LENGTH)]


class PayloadRequest(BaseModel):
    list_1: list[Item] = Field(min_length=1, max_length=MAX_ITEMS)
    list_2: list[Item] = Field(min_length=1, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def _lists_have_same_length(self) -> "PayloadRequest":
        if len(self.list_1) != len(self.list_2):
            raise ValueError("list_1 and list_2 must have the same length")
        return self


class PayloadCreated(BaseModel):
    id: str


class PayloadResponse(BaseModel):
    output: str | None
