"""Pydantic models for API request and response validation."""

import re

from pydantic import BaseModel, Field, field_validator


class UploadFileResponse(BaseModel):
    """Single file entry in an upload response.

    Attributes:
        id: UUID hex string assigned to the uploaded file.
        filename: Original filename as supplied by the client.
    """

    id: str = Field(..., description="UUID hex identifier for the uploaded file")
    filename: str = Field(..., description="Original filename from the client")


class UploadResponse(BaseModel):
    """Response returned after a successful batch upload.

    Attributes:
        uploaded: One entry per successfully saved file.
    """

    uploaded: list[UploadFileResponse] = Field(
        ...,
        description="Uploaded files with their assigned IDs",
    )


class ProcessRequest(BaseModel):
    """Request body for POST /process.

    Attributes:
        file_ids: IDs returned by a prior /upload call.
            Each must be a 32-character lowercase hex string.
            Minimum 1, maximum 100 IDs per request.
    """

    file_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="File IDs to extract (max 100)",
    )

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v: list[str]) -> list[str]:
        """Reject any ID that is not a 32-character hex string."""
        for file_id in v:
            if not re.match(r"^[a-f0-9]{32}$", file_id):
                raise ValueError(
                    f"Invalid file ID '{file_id}' — must be 32 hex characters."
                )
        return v


class ProcessResponse(BaseModel):
    """Response returned after extraction is queued.

    Attributes:
        status: Always ``"processing_started"`` on success.
    """

    status: str = Field(..., description="Confirmation that processing was queued")
