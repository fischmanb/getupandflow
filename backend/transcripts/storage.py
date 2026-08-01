"""Storage selection for raw transcript VTT files.

Same R2 backend the app already uses for profile photos (accounts.storage),
pointed at the transcripts/ prefix. FAILURE RULE mirrors photos: a missing R2
env must never crash the app — we fall back to local FileSystemStorage. Unlike
photos there is no upload API to reject, so the fallback is a real (dev-only)
write target; production sets R2_* and everything lands in the bucket.
"""

from django.core.files.storage import FileSystemStorage

from accounts.storage import R2MediaStorage, is_configured


def select_transcript_storage():
    if is_configured():
        return R2MediaStorage()
    return FileSystemStorage()
