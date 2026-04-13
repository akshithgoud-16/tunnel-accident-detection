from ultralytics import YOLO
import cv2
from deep_sort_realtime.deepsort_tracker import DeepSort
import math


model = YOLO("yolov8m.pt")
tracker = DeepSort(max_age=30)

cap = cv2.VideoCapture("videos/wrong-1.mp4")

prev_pos = {}
vehicle_status = {}

# Line geometry controls (edit these manually)
LINE_COUNT = 5
LINE_X1_RATIO = 0.20
LINE_X2_RATIO = 0.80
# y = m*x + c in normalized coordinates (x,y in [0..1] relative to frame size)
LINE_Y_INTERCEPT_RATIO = 0.12
LINE_SLOPE_PER_X_RATIO = 0.66
LINE_SPACING_PX = 70
# Global vertical shift for all lines: negative moves up, positive moves down
LINE_STACK_SHIFT_Y_PX = 0
# Keep the bottom-most line inside the frame with a small margin
LINE_BOTTOM_MARGIN_PX = 8

# Create parallel lines from configurable slope and position

def get_lines(w, h):
    lines = []

    # 🔥 CONFIG
    angle_deg = 10
    slope = math.tan(math.radians(angle_deg))  # ≈ -0.176

    LINE_SPACING_PX = 70
    LINE_COUNT = 5

    # 🔥 START FROM BOTTOM (IMPORTANT)
    y_base = h - 5   # small margin from bottom

    # choose x range safely inside frame
    x1 = int(w * 0.1)
    x2 = int(w * 0.9)

    # compute corresponding y using slope
    # y = y_base + slope*(x - x1)
    y1 = y_base
    y2 = int(y1 + slope * (x2 - x1))

    # 🔥 ensure both points are inside frame
    if y2 < 0:
        shift = abs(y2)
        y1 += shift
        y2 += shift
    if y2 > h:
        shift = y2 - h
        y1 -= shift
        y2 -= shift

    # 🔥 CREATE MULTIPLE PARALLEL LINES
    for i in range(LINE_COUNT):
        offset = i * LINE_SPACING_PX

        lines.append((
            (x1, y1 - offset),
            (x2, y2 - offset)
        ))

    return lines

# 🔥 POINT SIDE FUNCTION
def point_side(px, py, x1, y1, x2, y2):
    return (px - x1)*(y2 - y1) - (py - y1)*(x2 - x1)

def get_center(x1, y1, x2, y2):
    return int((x1+x2)/2), int((y1+y2)/2)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w, _ = frame.shape
    lines = get_lines(w, h)

    results = model(frame)
    detections = []

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            if conf < 0.5:
                continue

            if cls not in [2,3,5,7]:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append(([x1, y1, x2-x1, y2-y1], conf, cls))

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

        # 🔥 CHECK CROSSING
        for (p1, p2) in lines:
            prev_side = point_side(px, py, *p1, *p2)
            curr_side = point_side(cx, cy, *p1, *p2)

            if prev_side * curr_side < 0:
                # 🔥 MOVEMENT VALUE
                movement = curr_side - prev_side

                # 🔥 FIXED DIRECTION (REVERSED LOGIC)
                if movement > 0:
                    vehicle_status[track_id] = "wrong"   # flipped
                else:
                    pass  # still correct

        # 🔥 DRAW
        if vehicle_status[track_id] == "wrong":
            color = (0, 0, 255)
            label = f"ID {track_id} WRONG"
        else:
            color = (0, 255, 0)
            label = f"ID {track_id}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # 🔥 DRAW LINES
    for (p1, p2) in lines:
        cv2.line(frame, p1, p2, (255, 0, 0), 2)

    # 🔥 DISPLAY FIX
    screen_w, screen_h = 900, 900
    scale = min(screen_w / w, screen_h / h)
    frame_resized = cv2.resize(frame, (int(w*scale), int(h*scale)))

    cv2.imshow("Final Wrong Way Detection", frame_resized)

    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()