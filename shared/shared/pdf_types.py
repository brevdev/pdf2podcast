from fastapi import UploadFile, Form, File
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

class PDFFileUpload:
    def __init__(
        self,
        file: UploadFile = File(...),
        type: Literal["target", "context"] = Form(...)
    ):
        self.file = file
        self.type = type

FileTypeTuple = Tuple[UploadFile, Literal["target", "context"]]
FileContentTuple = Tuple[bytes, Literal["target", "context"]]