from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)

class Region(BaseModel):
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def bounds(self):
        if self.x + self.w > 1.00001 or self.y + self.h > 1.00001:
            raise ValueError('Vùng chọn vượt khỏi ảnh')
        if self.end is not None and self.end <= self.start:
            raise ValueError('Thời gian kết thúc phải lớn hơn bắt đầu')
        return self

class Stroke(BaseModel):
    points: list[Point] = Field(min_length=1, max_length=10000)
    width: float = Field(gt=0, le=.2)
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def times(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError('Thời gian kết thúc phải lớn hơn bắt đầu')
        return self

class Settings(BaseModel):
    regions: list[Region] = Field(default_factory=list, max_length=100)
    strokes: list[Stroke] = Field(default_factory=list, max_length=500)
    template_id: str | None = None
    search: Region | None = None
    threshold: float = Field(default=.65, ge=.1, le=.99)
    scale_min: float = Field(default=.75, ge=.1, le=4)
    scale_max: float = Field(default=1.25, ge=.1, le=4)
    max_matches: int = Field(default=3, ge=1, le=20)
    moving: bool = False
    method: Literal['telea', 'ns'] = 'telea'
    radius: int = Field(default=3, ge=1, le=15)
    expand: int = Field(default=3, ge=0, le=30)
    encoder: Literal['libx264', 'h264_nvenc', 'h264_qsv', 'h264_amf'] = 'libx264'
    crf: int = Field(default=18, ge=12, le=28)

    @model_validator(mode='after')
    def scales(self):
        if self.scale_max < self.scale_min:
            raise ValueError('Kích thước tối đa nhỏ hơn tối thiểu')
        return self

class PreviewRequest(BaseModel):
    asset_id: str
    settings: Settings
    time: float = Field(default=0, ge=0)

class JobRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    settings: Settings
    clip_start: float = Field(default=0, ge=0)
    clip_duration: float | None = Field(default=None, gt=0, le=10)

class CropRequest(BaseModel):
    asset_id: str
    time: float = Field(default=0, ge=0)
    region: Region

class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    settings: Settings
