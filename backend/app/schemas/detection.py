from pydantic import BaseModel


class DetectionEventRead(BaseModel):
    id: int
    run_id: int
    event_type: str
    track_id: int | None = None
    timestamp_ms: int
    details: dict | None = None

    class Config:
        from_attributes = True


class DetectionRunRead(BaseModel):
    id: int
    original_filename: str
    stored_video_path: str
    duration_ms: int
    wrong_way_count: int
    stop_count: int
    event_summary: list[dict] | dict | None = None

    class Config:
        from_attributes = True
