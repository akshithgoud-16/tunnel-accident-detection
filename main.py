from __future__ import annotations

import argparse

from backend.app.video.processor import DEFAULT_MODEL_PATH, run_video_demo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tunnel accident detection launcher")
    parser.add_argument("--video", required=True, help="Path to the input video")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Path to the YOLO model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_video_demo(video_path=args.video, model_path=args.model)


if __name__ == "__main__":
    main()