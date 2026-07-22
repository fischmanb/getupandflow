import os

from django.core.files.storage import FileSystemStorage
from storages.backends.s3 import S3Storage


def _r2_env():
    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key_id = os.getenv("R2_ACCESS_KEY_ID")
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")
    if not (account_id and access_key_id and secret_access_key and bucket):
        return None
    return {
        "account_id": account_id,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "bucket": bucket,
        "public_base_url": os.getenv("R2_PUBLIC_BASE_URL"),
    }


def is_configured():
    return _r2_env() is not None


class R2MediaStorage(S3Storage):
    """Media storage on Cloudflare R2 via its S3-compatible API.

    Credentials come from R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    and R2_BUCKET. When R2_PUBLIC_BASE_URL is set (a public bucket URL), files
    are served from it directly; otherwise URLs are signed per request.
    """

    def __init__(self, **settings_overrides):
        env = _r2_env()
        if env is None:
            raise RuntimeError(
                "Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET to enable photo storage."
            )
        defaults = {
            "access_key": env["access_key_id"],
            "secret_key": env["secret_access_key"],
            "bucket_name": env["bucket"],
            "endpoint_url": f"https://{env['account_id']}.r2.cloudflarestorage.com",
            "region_name": "auto",
            "file_overwrite": False,
            "default_acl": None,
        }
        if env["public_base_url"]:
            public_host = env["public_base_url"].removeprefix("https://").removeprefix("http://").rstrip("/")
            defaults["custom_domain"] = public_host
            defaults["querystring_auth"] = False
        super().__init__(**{**defaults, **settings_overrides})


def select_photo_storage():
    """Pick the storage for profile photos when models load.

    FAILURE RULE: missing R2 env must never crash the app. Without it we fall
    back to local storage, and the API rejects photo uploads with a clear 400
    (see validate_photo_upload) so nothing is ever written to the fallback.
    """
    if is_configured():
        return R2MediaStorage()
    return FileSystemStorage()
