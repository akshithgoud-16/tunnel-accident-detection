from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionConfig:
    confidence_threshold: float = 0.5
    vehicle_classes: tuple[int, ...] = (2, 3, 5, 7)
