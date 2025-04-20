from pydantic import BaseModel, model_validator

from typing import Self

from pydantic import Field, ValidationError
from pydantic.functional_validators import field_validator

from . import db
from .common_passwords import COMMON_PASSWORDS
from .reserved_slugs import RESERVED_SLUGS


MINIMUM_CHARACTERS = 8


class Signup(BaseModel):
    name: str = Field(min_length=1)
    account_slug: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str
    password_check: str

    @field_validator("account_slug")
    @classmethod
    def check_account_slug(cls, account_slug: str) -> str:
        if account_slug.lower() in RESERVED_SLUGS:
            raise ValueError(
                "Slug is reserved, if this is your organization email support@textualize.io"
            )
        return account_slug

    @field_validator("email")
    @classmethod
    def check_email(cls, email: str) -> str:
        if "@" not in email:
            raise ValueError("Email is invalid")
        return email

    @field_validator("password")
    @classmethod
    def check_password_field(cls, password: str) -> str:
        if len(password) < MINIMUM_CHARACTERS:
            raise ValueError(
                f"Password must be {MINIMUM_CHARACTERS} characters or longer"
            )
        if password.lower() in COMMON_PASSWORDS:
            raise ValueError("password is too common")
        return password

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.password != self.password_check:
            raise ValueError("Passwords do not match")
        return self
