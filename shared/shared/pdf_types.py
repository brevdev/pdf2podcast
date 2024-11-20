from fastapi import UploadFile
from pydantic import BaseModel, Field
from typing import Optional, Union, Literal, Tuple
from datetime import datetime
from enum import Enum


class ConversionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class PDFConversionResult(BaseModel):
    filename: str
    content: str = ""
    status: ConversionStatus
    error: Optional[str] = None


class PDFMetadata(BaseModel):
    filename: str
    markdown: str = ""
    summary: str = ""
    type: Union[Literal["target"], Literal["context"]]
    status: ConversionStatus
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


FileTypeTuple = Tuple[UploadFile, Literal["target", "context"]]
FileContentTuple = Tuple[bytes, Literal["target", "context"]]
