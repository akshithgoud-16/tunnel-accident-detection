from __future__ import annotations

import math
from pathlib import Path

import cv2
from deep_sort_realtime.deepsort_tracker import DeepSort
from ultralytics import YOLO


DEFAULT_MODEL_PATH = Path("backend/app/ml/weights/yolov8m.pt")


def get_lines(w: int, h: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    lines: list[tuple[tuple[int, int], tuple[int, int]]] = []
    angle_deg = 10
    slope = math.tan(math.radians(angle_deg))
    line_spacing_px = 70
    line_count = 5

    y_base = h - 5
    x1 = int(w * 0.1)
    x2 = int(w * 0.9)
    y1 = y_base
    y2 = int(y1 + slope * (x2 - x1))

    if y2 < 0:
        shift = abs(y2)
        y1 += shift
        y2 += shift
    if y2 > h:
        shift = y2 - h
        y1 -= shift
        y2 -= shift

    for index in range(line_count):
        offset = index * line_spacing_px
        lines.append(((x1, y1 - offset), (x2, y2 - offset)))

    return lines


def point_side(px: int, py: int, x1: int, y1: int, x2: int, y2: int) -> int:
    return (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)


def get_center(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def run_video_demo(video_path: str | Path, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
    model = YOLO(str(model_path))
    tracker = DeepSort(max_age=30)
    cap = cv2.VideoCapture(str(video_path))

    prev_pos: dict[int, tuple[int, int]] = {}
    vehicle_status: dict[int, str] = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w, _ = frame.shape
        lines = get_lines(w, h)

        results = model(frame)
        detections = []

        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])

                if conf < 0.5:
                    continue

                if cls not in [2, 3, 5, 7]:
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
                vehicle_status[track_id] = "correct"
                continue

            px, py = prev_pos[track_id]
            prev_pos[track_id] = (cx, cy)

            for p1, p2 in lines:
                prev_side = point_side(px, py, *p1, *p2)
                curr_side = point_side(cx, cy, *p1, *p2)

                if prev_side * curr_side < 0:
                    movement = curr_side - prev_side
                    if movement > 0:
                        vehicle_status[track_id] = "wrong"

            if vehicle_status[track_id] == "wrong":
                color = (0, 0, 255)
                label = f"ID {track_id} WRONG"
            else:
                color = (0, 255, 0)
                label = f"ID {track_id}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        for p1, p2 in lines:
            cv2.line(frame, p1, p2, (255, 0, 0), 2)

        screen_w, screen_h = 900, 900
        scale = min(screen_w / w, screen_h / h)
        frame_resized = cv2.resize(frame, (int(w * scale), int(h * scale)))

        cv2.imshow("Final Wrong Way Detection", frame_resized)

        if cv2.waitKey(1) == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_video_demo()
