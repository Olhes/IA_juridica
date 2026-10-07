"""Shared, strict user-input contracts for legal queries and chat."""

from typing import Annotated, Literal, Any
import json

from pydantic import AfterValidator, StringConstraints

SupportedLanguage = Literal["spanish", "quechua"]
NonBlankMessage = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)
]


def validate_context(value):
    if len(json.dumps(value, ensure_ascii=False, default=str)) > 3500:
        raise ValueError("Context exceeds 3500 characters")
    return value


RequestContext = Annotated[dict[str, Any], AfterValidator(validate_context)]
