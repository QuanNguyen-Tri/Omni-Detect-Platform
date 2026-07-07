from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DetectionKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: Optional[Any] = None


class DetectTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=100_000)
    estimated_cost: Optional[float] = Field(default=None, gt=0, le=1_000)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class TextSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)
    text: str
    ai_probability: float = Field(..., ge=0, le=1)
    label: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> "TextSpan":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class TextDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_ai_probability: float = Field(..., ge=0, le=1)
    spans: List[TextSpan] = Field(default_factory=list)


class ImageRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    ai_probability: float = Field(..., ge=0, le=1)
    label: str = Field(..., min_length=1)


class ImageDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_ai_probability: float = Field(..., ge=0, le=1)
    regions: List[ImageRegion] = Field(default_factory=list)


class FileSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    start_page: Optional[int] = Field(default=None, ge=1)
    end_page: Optional[int] = Field(default=None, ge=1)
    ai_probability: float = Field(..., ge=0, le=1)
    label: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "FileSection":
        if (
            self.start_page is not None
            and self.end_page is not None
            and self.end_page < self.start_page
        ):
            raise ValueError("end_page must be greater than or equal to start_page")
        return self


class FileDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_ai_probability: float = Field(..., ge=0, le=1)
    sections: List[FileSection] = Field(default_factory=list)


DetectionResult = Union[TextDetectionResult, ImageDetectionResult, FileDetectionResult]


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    kind: DetectionKind
    estimated_cost: float
    status_url: str


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    kind: DetectionKind
    estimated_cost: float
    created_at: datetime
    updated_at: datetime
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[DetectionResult] = None
    error: Optional[ErrorDetail] = None

