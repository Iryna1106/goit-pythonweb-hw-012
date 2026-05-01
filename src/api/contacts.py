"""Contact CRUD routes (``/api/contacts``).

All endpoints require a valid access token and operate on the caller's own
contacts only.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.database.db import get_db
from src.database.models import User
from src.repository import contacts as repo_contacts
from src.schemas.contacts import ContactCreate, ContactResponse, ContactUpdate
from src.services.auth import get_current_user

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/", response_model=List[ContactResponse])
def read_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    first_name: Optional[str] = Query(None, description="Фільтр за іменем (частковий збіг)"),
    last_name: Optional[str] = Query(None, description="Фільтр за прізвищем (частковий збіг)"),
    email: Optional[str] = Query(None, description="Фільтр за email (частковий збіг)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the caller's contacts with pagination and optional partial filters."""
    return repo_contacts.get_contacts(
        db,
        current_user,
        skip=skip,
        limit=limit,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )


@router.get("/upcoming-birthdays", response_model=List[ContactResponse])
def upcoming_birthdays(
    days: int = Query(7, ge=1, le=365, description="Кількість днів наперед"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return contacts whose birthday falls within the next ``days`` days."""
    return repo_contacts.get_upcoming_birthdays(db, current_user, days=days)


@router.get("/{contact_id}", response_model=ContactResponse)
def read_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return one of the caller's contacts; 404 if missing or owned by someone else."""
    contact = repo_contacts.get_contact(db, current_user, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    body: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new contact owned by the caller; 409 if the email is already used."""
    if repo_contacts.get_contact_by_email(db, current_user, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contact with this email already exists",
        )
    return repo_contacts.create_contact(db, current_user, body)


@router.put("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partially update a caller-owned contact."""
    if body.email:
        existing = repo_contacts.get_contact_by_email(db, current_user, body.email)
        if existing and existing.id != contact_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another contact with this email already exists",
            )
    contact = repo_contacts.update_contact(db, current_user, contact_id, body)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.delete("/{contact_id}", response_model=ContactResponse)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a caller-owned contact and return its final representation."""
    contact = repo_contacts.delete_contact(db, current_user, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact
