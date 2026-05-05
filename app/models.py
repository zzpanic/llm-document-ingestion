"""Pydantic models for API request and response validation.

Provides automatic request validation, OpenAPI schema generation,
and type-safe data transfer between layers.

All models follow Google style docstrings with Args, Returns, and
Raises sections where applicable.
"""

import re
from typing import List

from pydantic import BaseModel, Field, field_validator


class UploadFileResponse(BaseModel):
    """Response item for a single uploaded file.

    Attributes:
        id: Unique identifier for the uploaded file.
        filename: Original filename of the uploaded file.
    """

    id: str = Field(..., description="Unique identifier for the uploaded file")
    filename: str = Field(..., description="Original filename of the uploaded file")


class UploadResponse(BaseModel):
    """Response returned after successful image upload.

    Attributes:
        uploaded: List of uploaded file info dictionaries containing id and filename.
    """

    uploaded: List[UploadFileResponse] = Field(
        ...,
        description="List of uploaded file IDs and filenames"
    )


class ProcessRequest(BaseModel):
    """Request to trigger extraction on uploaded images.

    Attributes:
        file_ids: List of uploaded file IDs to process. Must contain at least one ID.
                 Each ID must be a valid UUID hex string (32 characters).
    """

    file_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of uploaded file IDs to process (max 100)"
    )

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v: List[str]) -> List[str]:
        """Validate that each file_id is a valid UUID hex string.

        Args:
            v: List of file IDs to validate.

        Returns:
            The validated list of file IDs.

        Raises:
            ValueError: If any file_id is not a valid UUID hex string.
        """
        for file_id in v:
            if not re.match(r"^[a-f0-9]{32}$", file_id):
                raise ValueError(f"Invalid file ID format: {file_id}. Must be 32 hex characters.")
        return v


class ProcessResponse(BaseModel):
    """Response indicating extraction has been queued.

    Attributes:
        status: Processing status indicator string.
    """

    status: str = Field(
        ...,
        description="Processing status indicator"
    )


class StatusEntry(BaseModel):
    """Status information for a single extracted file.

    Attributes:
        state: Extraction state - one of 'pending', 'processing', 'done', 'failed'.
        markdown_length: Length of extracted markdown in characters, if done.
        error: Error message if state is 'failed'.
    """

    state: str = Field(
        ...,
        description="Extraction state: pending, processing, done, failed"
    )
    markdown_length: int | None = Field(
        None,
        description="Length of extracted markdown in characters"
    )
    error: str | None = Field(
        None,
        description="Error message if state is 'failed'"
    )


class StatusResponse(BaseModel):
    """Aggregate status response for all tracked files.

    Attributes:
        status: Dictionary mapping file IDs to their status objects.
    """

    status: dict[str, dict[str, object]] = Field(
        ...,
        description="Per-file extraction status map"
    )


class DownloadMetadata(BaseModel):
    """Download response metadata.

    Attributes:
        filename: Name of the downloadable file.
        content_type: MIME type of the file.
    """

    filename: str = Field(..., description="Name of the downloadable file")
    content_type: str = Field(..., description="MIME type of the file")