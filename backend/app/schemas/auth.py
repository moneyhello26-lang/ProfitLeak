import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Role = Literal["owner", "analyst", "viewer"]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class EmailPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Укажите корректный email.")
        return value


class RegisterRequest(EmailPayload):
    password: Password
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class LoginRequest(EmailPayload):
    password: str = Field(min_length=1, max_length=128)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: str


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    business_id: UUID
    role: Role


class AuthRead(BaseModel):
    user: UserRead
    memberships: list[MembershipRead]


class MemberRead(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: Role


class AddMemberRequest(EmailPayload):
    role: Role


class ChangeRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
