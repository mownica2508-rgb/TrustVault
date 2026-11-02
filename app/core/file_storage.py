import hashlib
import os
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


class UploadRejected(ValueError):
    def __init__(self, message: str, status_code: int = 415):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    storage_name: str
    content_type: str
    size_bytes: int
    sha256: str


def storage_root() -> Path:
    settings = get_settings()
    root = settings.resolved_storage_dir
    static_root = (Path(__file__).resolve().parents[1] / "static").resolve()
    if root == static_root or static_root in root.parents:
        raise RuntimeError("Private document storage cannot be inside the public static directory")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_original_filename(filename: str | None) -> tuple[str, str]:
    if not filename:
        raise UploadRejected("A filename is required")
    normalized = filename.replace("\\", "/").split("/")[-1].strip()
    if not normalized or normalized in {".", ".."} or len(normalized) > 255:
        raise UploadRejected("The filename is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise UploadRejected("Control characters are not allowed in filenames")
    suffix = Path(normalized).suffix.lower()
    if suffix not in MIME_TYPES:
        raise UploadRejected("Only PDF, DOCX, and TXT files are accepted")
    return normalized, suffix


def _validate_file(path: Path, suffix: str) -> str:
    if suffix == ".pdf":
        with path.open("rb") as uploaded:
            if not uploaded.read(5).startswith(b"%PDF-"):
                raise UploadRejected("The file content does not match a PDF document")
    elif suffix == ".txt":
        try:
            with path.open("r", encoding="utf-8-sig") as uploaded:
                for line in uploaded:
                    if "\x00" in line:
                        raise UploadRejected("Text files cannot contain binary data")
        except UnicodeDecodeError:
            raise UploadRejected("Text files must use UTF-8 encoding")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise UploadRejected("The file is not a valid DOCX document")
                if len(entries) > 2000:
                    raise UploadRejected("The DOCX package contains too many entries")
                if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise UploadRejected("The DOCX package contains an unsafe path")
                if sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
                    raise UploadRejected("The DOCX expands beyond the allowed document size")
        except (zipfile.BadZipFile, OSError):
            raise UploadRejected("The file is not a valid DOCX document")
    return MIME_TYPES[suffix]


def save_upload(source: BinaryIO, filename: str | None) -> StoredUpload:
    original_filename, suffix = _safe_original_filename(filename)
    settings = get_settings()
    root = storage_root()
    digest = hashlib.sha256()
    size = 0
    temp_path: Path | None = None
    final_name = f"{uuid.uuid4().hex}{suffix}"
    final_path = root / final_name
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=root, prefix=".incoming-", delete=False) as temp:
            temp_path = Path(temp.name)
            while chunk := source.read(64 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadRejected(
                        f"The upload exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
                        status_code=413,
                    )
                digest.update(chunk)
                temp.write(chunk)
        if size == 0:
            raise UploadRejected("Empty files cannot be uploaded")
        content_type = _validate_file(temp_path, suffix)
        os.replace(temp_path, final_path)
        temp_path = None
        return StoredUpload(
            original_filename=original_filename,
            storage_name=final_name,
            content_type=content_type,
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def stored_path(storage_name: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|docx|txt)", storage_name):
        raise FileNotFoundError("Invalid internal storage key")
    return storage_root() / storage_name


def remove_stored_file(storage_name: str) -> None:
    stored_path(storage_name).unlink(missing_ok=True)
