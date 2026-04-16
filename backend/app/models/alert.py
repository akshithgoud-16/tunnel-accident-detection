from sqlalchemy import Column, DateTime, Integer, String, func

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    video_name = Column(String, nullable=False)
    violation_type = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    track_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)