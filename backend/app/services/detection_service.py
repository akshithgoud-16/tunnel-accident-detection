from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from collections import deque
from pathlib import Path

import cv2
from deep_sort_realtime.deepsort_tracker import DeepSort
from sqlalchemy.orm import Session
from ultralytics import YOLO

from app.core.config import get_settings
from app.models.incident import DetectionEvent, DetectionRun
from app.video.processor import get_center, get_lines, point_side

settings = get_settings()
MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "weights" / "yolov8m.pt"
DEFAULT_PLAYBACK_FPS = 30.0


def _motion_metrics(points: deque[tuple[int, int]]) -> tuple[float, float]:
    if len(points) < 2:
        return 0.0, 0.0

    path_distance = 0.0
    previous = points[0]
    for current in list(points)[1:]:
        path_distance += math.hypot(current[0] - previous[0], current[1] - previous[1])
        previous = current

    first = points[0]
    last = points[-1]
    net_displacement = math.hypot(last[0] - first[0], last[1] - first[1])
    return path_distance, net_displacement


def save_uploaded_video(content: bytes, original_filename: str) -> Path:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(original_filename).suffix or ".mp4"
    target_name = f"{uuid.uuid4().hex}{extension}"
    target_path = settings.uploads_dir / target_name
    target_path.write_bytes(content)
    return target_path


def get_analyzed_video_path(video_path: Path) -> Path:
    # Always write analyzed output as MP4 so browser playback works in dashboard.
    return video_path.with_name(f"{video_path.stem}_analyzed.mp4")


def get_existing_analyzed_video_path(video_path: Path) -> Path | None:
    mp4_path = get_analyzed_video_path(video_path)
    if mp4_path.exists():
        return mp4_path

    # Backward compatibility for older analyzed files stored with original suffix.
    legacy_suffix = video_path.suffix or ".mp4"
    legacy_path = video_path.with_name(f"{video_path.stem}_analyzed{legacy_suffix}")
    if legacy_path.exists():
        return legacy_path

    return None


def get_stream_playback_fps(source_fps: float | int | None) -> float:
    """Keep streaming playback closer to the previous processed/demo pace."""
    if not source_fps or float(source_fps) <= 0:
        return DEFAULT_PLAYBACK_FPS

    # Cap playback at a higher value so movement/stops are visible sooner in stream.
    return min(float(source_fps), DEFAULT_PLAYBACK_FPS)


def process_video_upload(
    db: Session,
    video_path: Path,
    original_filename: str,
    run_id: int | None = None,
    frame_callback: Callable[[bytes], None] | None = None,
) -> DetectionRun:
    model = YOLO(str(MODEL_PATH))
    tracker = DeepSort(max_age=30)
    cap = cv2.VideoCapture(str(video_path))
    analyzed_path = get_analyzed_video_path(video_path)
    writer: cv2.VideoWriter | None = None
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 0
    analysis_fps = float(source_fps) if source_fps and source_fps > 0 else 24.0

    # FPS-aware stop detection thresholds to avoid frame-rate dependent behavior.
    stop_min_seconds = 2.2
    stop_window_seconds = 1.2
    min_stop_frames = max(8, int(analysis_fps * stop_min_seconds))
    window_frames = max(6, int(analysis_fps * stop_window_seconds))
    stop_jitter_px = 1.2
    stop_release_px = 4.0
    max_window_net_displacement = 6.0
    max_window_path_distance = max(8.0, window_frames * 0.8)
    max_stationary_speed = 7.0

    prev_pos: dict[int, tuple[int, int]] = {}
    wrong_way_flags: dict[int, bool] = {}
    stop_flags: dict[int, bool] = {}
    stop_frames: dict[int, int] = {}
    track_motion: dict[int, deque[tuple[int, int]]] = {}
    wrong_way_count = 0
    stop_count = 0
    event_summary: list[dict[str, object]] = []
    pending_events: list[DetectionEvent] = []
    last_frame_ms = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if writer is None:
            frame_h, frame_w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(analyzed_path), fourcc, analysis_fps, (frame_w, frame_h))

        last_frame_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
        h, w, _ = frame.shape
        lines = get_lines(w, h)

        results = model(frame)
        detections = []

        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])

                if conf < 0.5 or cls not in [2, 3, 5, 7]:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(([x1, y1, x2 - x1, y2 - y1], conf, cls))

        tracks = tracker.update_tracks(detections, frame=frame)

        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id = track.track_id
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            cx, cy = get_center(x1, y1, x2, y2)

            if track_id not in prev_pos:
                prev_pos[track_id] = (cx, cy)
                wrong_way_flags[track_id] = False
                stop_flags[track_id] = False
                stop_frames[track_id] = 0
                history = deque(maxlen=window_frames)
                history.append((cx, cy))
                track_motion[track_id] = history
                continue

            px, py = prev_pos[track_id]
            prev_pos[track_id] = (cx, cy)

            moved = abs(cx - px) + abs(cy - py)
            if moved <= stop_jitter_px:
                stop_frames[track_id] = stop_frames.get(track_id, 0) + 1
            else:
                stop_frames[track_id] = 0

            history = track_motion.setdefault(track_id, deque(maxlen=window_frames))
            history.append((cx, cy))
            window_path, window_net = _motion_metrics(history)
            window_speed = window_path / stop_window_seconds

            is_stop_candidate = (
                stop_frames[track_id] >= min_stop_frames
                and window_path <= max_window_path_distance
                and window_net <= max_window_net_displacement
                and window_speed <= max_stationary_speed
                and moved <= stop_jitter_px
            )

            if is_stop_candidate and not stop_flags.get(track_id, False):
                stop_flags[track_id] = True
                stop_count += 1
                event_summary.append({"type": "stop", "track_id": track_id, "timestamp_ms": last_frame_ms})
                pending_events.append(
                    DetectionEvent(
                        event_type="stop",
                        track_id=track_id,
                        timestamp_ms=last_frame_ms,
                        details={
                            "movement": moved,
                            "window_path": round(window_path, 2),
                            "window_net": round(window_net, 2),
                        },
                    )
                )
            elif not is_stop_candidate and moved >= stop_release_px:
                stop_flags[track_id] = False

            for p1, p2 in lines:
                prev_side = point_side(px, py, *p1, *p2)
                curr_side = point_side(cx, cy, *p1, *p2)

                if prev_side * curr_side < 0:
                    movement = curr_side - prev_side
                    if movement > 0 and not wrong_way_flags.get(track_id, False):
                        wrong_way_flags[track_id] = True
                        wrong_way_count += 1
                        event_summary.append({"type": "wrong_way", "track_id": track_id, "timestamp_ms": last_frame_ms})
                        pending_events.append(
                            DetectionEvent(
                                event_type="wrong_way",
                                track_id=track_id,
                                timestamp_ms=last_frame_ms,
                                details={"movement": movement},
                            )
                        )

            if stop_flags.get(track_id):
                color = (0, 165, 255)
                label = f"ID {track_id} STOP"
            elif wrong_way_flags.get(track_id):
                color = (0, 0, 255)
                label = f"ID {track_id} WRONG"
            else:
                color = (0, 255, 0)
                label = f"ID {track_id}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        cv2.putText(
            frame,
            f"Wrong-way: {wrong_way_count} | Stops: {stop_count}",
            (16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        if writer is not None:
            writer.write(frame)

        if frame_callback is not None:
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                frame_callback(buffer.tobytes())

    cap.release()
    if writer is not None:
        writer.release()

    if run_id is None:
        run = DetectionRun(
            original_filename=original_filename,
            stored_video_path=str(video_path),
            duration_ms=last_frame_ms,
            wrong_way_count=wrong_way_count,
            stop_count=stop_count,
            event_summary=event_summary,
        )
        db.add(run)
        db.flush()
    else:
        run = db.query(DetectionRun).filter(DetectionRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Detection run {run_id} was not found")

        run.original_filename = original_filename
        run.stored_video_path = str(video_path)
        run.duration_ms = last_frame_ms
        run.wrong_way_count = wrong_way_count
        run.stop_count = stop_count
        run.event_summary = event_summary

        db.query(DetectionEvent).filter(DetectionEvent.run_id == run.id).delete()
        db.flush()

    for event in pending_events:
        event.run_id = run.id
        db.add(event)

    db.commit()
    db.refresh(run)
    return run
