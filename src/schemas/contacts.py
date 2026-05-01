from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=50, examples=["Ivan"])
    last_name: str = Field(min_length=1, max_length=50, examples=["Franko"])
    email: EmailStr = Field(examples=["ivan.franko@example.com"])
    phone: str = Field(min_length=3, max_length=30, examples=["+380501234567"])
    birthday: date = Field(examples=["1990-05-17"])
    additional_info: Optional[str] = Field(default=None, max_length=500)


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=3, max_length=30)
    birthday: Optional[date] = None
    additional_info: Optional[str] = Field(default=None, max_length=500)


class ContactResponse(ContactBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
