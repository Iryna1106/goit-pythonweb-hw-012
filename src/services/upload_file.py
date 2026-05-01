import cloudinary
import cloudinary.uploader

from src.conf.config import settings


class UploadFileService:
    def __init__(self) -> None:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )

    @staticmethod
    def upload_avatar(file, username: str) -> str:
        public_id = f"contacts_api/avatars/{username}"
        result = cloudinary.uploader.upload(
            file, public_id=public_id, overwrite=True, resource_type="image"
        )
        version = result.get("version")
        return cloudinary.CloudinaryImage(public_id).build_url(
            width=250, height=250, crop="fill", version=version
        )
