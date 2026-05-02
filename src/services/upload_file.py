"""Cloudinary integration for avatar uploads.

The :class:`UploadFileService` configures Cloudinary on instantiation
using credentials from :mod:`src.conf.config`. The avatar uploader
stores each user's avatar under a deterministic public ID
(``contacts_api/avatars/<username>``) and returns a CDN URL that
Cloudinary will serve as a 250x250 cropped image.
"""
import cloudinary
import cloudinary.uploader

from src.conf.config import settings


class UploadFileService:
    """Thin wrapper around the Cloudinary SDK for uploading user avatars."""

    def __init__(self) -> None:
        """Configure the Cloudinary SDK from environment-backed settings."""
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )

    @staticmethod
    def upload_avatar(file, username: str) -> str:
        """Upload an avatar to Cloudinary and return a sized CDN URL.

        Re-uploads to the same ``public_id`` overwrite previous avatars,
        so each user has at most one stored avatar at any time.

        Args:
            file: A file-like object (typically
                :attr:`fastapi.UploadFile.file`) containing image bytes.
            username: Used as part of the Cloudinary public ID.

        Returns:
            A versioned URL serving a 250x250 cropped variant.
        """
        public_id = f"contacts_api/avatars/{username}"
        result = cloudinary.uploader.upload(
            file, public_id=public_id, overwrite=True, resource_type="image"
        )
        version = result.get("version")
        return cloudinary.CloudinaryImage(public_id).build_url(
            width=250, height=250, crop="fill", version=version
        )
