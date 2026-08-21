import hashlib


def deduplicate_image_uploads(uploads):
    unique_uploads = []
    upload_indexes = []
    seen_hashes = {}
    for upload in uploads:
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        fingerprint = digest.hexdigest()
        if fingerprint not in seen_hashes:
            seen_hashes[fingerprint] = len(unique_uploads)
            unique_uploads.append(upload)
        upload_indexes.append(seen_hashes[fingerprint])
    return unique_uploads, upload_indexes
