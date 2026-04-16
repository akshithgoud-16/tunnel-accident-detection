from pydantic import BaseModel


class IncidentBase(BaseModel):
    incident_type: str
    severity: str = "medium"
    video_path: str | None = None


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase):
    id: int

    class Config:
        from_attributes = True
