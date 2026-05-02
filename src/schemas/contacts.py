"""Pydantic schemas for the contacts API.

* :class:`ContactBase` defines the field set shared between create and
  response payloads.
* :class:`ContactCreate` is the create payload — currently identical
  to :class:`ContactBase`, but kept distinct for forward-compatibility
  (e.g. server-side defaults).
* :class:`ContactUpdate` is a partial-update payload — every field is
  optional and routes apply ``model_dump(exclude_unset=True)``.
* :class:`ContactResponse` is the read schema, hydrated from the ORM
  row via ``from_attributes=True``.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactBase(BaseModel):
    """Shared fields between create and response schemas."""

    first_name: str = Field(min_length=1, max_length=50, examples=["Ivan"])
    last_name: str = Field(min_length=1, max_length=50, examples=["Franko"])
    email: EmailStr = Field(examples=["ivan.franko@example.com"])
    phone: str = Field(min_length=3, max_length=30, examples=["+380501234567"])
    birthday: date = Field(examples=["1990-05-17"])
    additional_info: Optional[str] = Field(default=None, max_length=500)


class ContactCreate(ContactBase):
    """Create payload for ``POST /api/contacts/``."""


class ContactUpdate(BaseModel):
    """Partial update payload for ``PUT /api/contacts/{id}``.

    Every field is optional; only fields explicitly present in the
    request body are written. Validation rules match
    :class:`ContactBase` for the fields that are sent.
    """

    first_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=3, max_length=30)
    birthday: Optional[date] = None
    additional_info: Optional[str] = Field(default=None, max_length=500)


class ContactResponse(ContactBase):
    """Read schema for ``GET`` endpoints — adds id + audit timestamps."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
