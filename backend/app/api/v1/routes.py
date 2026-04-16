import time
from threading import Lock, Thread
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pathlib import Path

import cv2
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.session import get_db
from app.models.incident import DetectionEvent, DetectionRun
from app.schemas.detection import DetectionEventRead, DetectionRunRead
from app.services.detection_service import (
    get_analyzed_video_path,
    get_existing_analyzed_video_path,
    get_stream_playback_fps,
    process_video_upload,
    save_uploaded_video,
)

router = APIRouter(tags=["system"])
_active_runs: set[int] = set()
_active_runs_lock = Lock()
_live_frames: dict[int, bytes] = {}
_live_frames_lock = Lock()


def _mark_run_active(run_id: int) -> None:
    with _active_runs_lock:
        _active_runs.add(run_id)


def _mark_run_inactive(run_id: int) -> None:
    with _active_runs_lock:
        _active_runs.discard(run_id)


def _is_run_active(run_id: int) -> bool:
    with _active_runs_lock:
        return run_id in _active_runs


def _set_live_frame(run_id: int, frame_bytes: bytes) -> None:
    with _live_frames_lock:
        _live_frames[run_id] = frame_bytes


def _get_live_frame(run_id: int) -> bytes | None:
    with _live_frames_lock:
        return _live_frames.get(run_id)


def _clear_live_frame(run_id: int) -> None:
    with _live_frames_lock:
        _live_frames.pop(run_id, None)


def _process_video_async(run_id: int, video_path: Path, original_filename: str) -> None:
    worker_db = SessionLocal()
    try:
        process_video_upload(
            worker_db,
            video_path,
            original_filename,
            run_id=run_id,
            frame_callback=lambda frame: _set_live_frame(run_id, frame),
        )
    finally:
        worker_db.close()
        _clear_live_frame(run_id)
        _mark_run_inactive(run_id)


def _video_url(file_path: str | Path | None) -> str | None:
    if not file_path:
        return None
    filename = Path(file_path).name
    return f"/uploads/{filename}"


def _video_fps(file_path: str | Path | None) -> float | None:
    if not file_path:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    cap.release()
    return round(float(fps), 2) if fps > 0 else None


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/runs", response_model=list[DetectionRunRead])
def list_runs(db: Session = Depends(get_db)) -> list[DetectionRun]:
    return db.query(DetectionRun).order_by(DetectionRun.id.desc()).all()


@router.get("/events", response_model=list[DetectionEventRead])
def list_events(db: Session = Depends(get_db)) -> list[DetectionEvent]:
    return db.query(DetectionEvent).order_by(DetectionEvent.id.desc()).all()


@router.post("/videos/upload", response_model=DetectionRunRead)
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)) -> DetectionRun:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A video filename is required")

    stored_path = save_uploaded_video(await file.read(), file.filename)

    run = DetectionRun(
        original_filename=file.filename,
        stored_video_path=str(stored_path),
        duration_ms=0,
        wrong_way_count=0,
        stop_count=0,
        event_summary=[],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _mark_run_active(run.id)
    Thread(
        target=_process_video_async,
        args=(run.id, stored_path, file.filename),
        daemon=True,
    ).start()

    return run


@router.get("/videos/analyzed/stream")
def stream_analyzed_video(run_id: int | None = None, db: Session = Depends(get_db)) -> StreamingResponse:
    if run_id is None:
        run = db.query(DetectionRun).order_by(DetectionRun.id.desc()).first()
    else:
        run = db.query(DetectionRun).filter(DetectionRun.id == run_id).first()

    if run is None:
        raise HTTPException(status_code=404, detail="No processed run found")

    analyzed_path = get_existing_analyzed_video_path(Path(run.stored_video_path))
    if analyzed_path is None:
        analyzed_path = get_analyzed_video_path(Path(run.stored_video_path))

    if not analyzed_path.exists() and not _is_run_active(run.id):
        raise HTTPException(status_code=404, detail="Analyzed video not found")

    def generate_frames() -> bytes:
        frame_delay = 1.0 / get_stream_playback_fps(None)
        cap: cv2.VideoCapture | None = None

        try:
            while True:
                if _is_run_active(run.id):
                    # Stream live JPEG frames from the processing loop while MP4 is still incomplete.
                    frame_bytes = _get_live_frame(run.id)
                    if frame_bytes is None:
                        time.sleep(0.05)
                        continue

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )

                    time.sleep(frame_delay)
                    continue

                if cap is None:
                    if not analyzed_path.exists():
                        break

                    cap = cv2.VideoCapture(str(analyzed_path))
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        break

                    fps = cap.get(cv2.CAP_PROP_FPS) or 0
                    frame_delay = 1.0 / get_stream_playback_fps(fps)

                ret, frame = cap.read()
                if not ret:
                    # Loop back to the beginning after processing has completed.
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                ok, buffer = cv2.imencode(".jpg", frame)
                if not ok:
                    continue

                frame_bytes = buffer.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

                time.sleep(frame_delay)
        finally:
            if cap is not None:
                cap.release()

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    latest_run = db.query(DetectionRun).order_by(DetectionRun.id.desc()).first()
    events = db.query(DetectionEvent).order_by(DetectionEvent.id.desc()).limit(10).all()

    analyzed_video_url = None
    analyzed_video_fps = None
    original_video_fps = None
    if latest_run is not None:
        original_path = Path(latest_run.stored_video_path)
        analyzed_path = get_existing_analyzed_video_path(original_path)
        original_video_fps = _video_fps(original_path)
        if analyzed_path is not None:
            analyzed_video_url = _video_url(analyzed_path)
            analyzed_video_fps = _video_fps(analyzed_path)

    return {
        "latest_run": None
        if latest_run is None
        else {
            "id": latest_run.id,
            "original_filename": latest_run.original_filename,
            "stored_video_path": latest_run.stored_video_path,
            "original_video_url": _video_url(latest_run.stored_video_path),
            "analyzed_video_url": analyzed_video_url,
            "original_video_fps": original_video_fps,
            "analyzed_video_fps": analyzed_video_fps,
            "duration_ms": latest_run.duration_ms,
            "wrong_way_count": latest_run.wrong_way_count,
            "stop_count": latest_run.stop_count,
            "event_summary": latest_run.event_summary,
        },
        "recent_events": [
            {
                "id": event.id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "track_id": event.track_id,
                "timestamp_ms": event.timestamp_ms,
                "details": event.details,
            }
            for event in events
        ],
    }
