"""
TRAFFIX AI - Computer Vision Vehicle Detection Module
Uses OpenCV to process live webcam or recorded traffic video feeds:
- Background subtraction (MOG2) & contour tracking
- Vehicle detection and bounding box visualization
- Virtual tripwire vehicle counting
- Lane occupancy estimation
- Clearly distinguished from SUMO microscopic simulation
"""

import cv2
import numpy as np
import time
import os
import threading
from typing import Dict, Any, Tuple, Optional


class CameraVehicleDetector:
    """
    OpenCV-based vehicle detector and tracker for video streams or webcams.
    """

    def __init__(self, min_contour_area: int = 600):
        self.min_area = min_contour_area
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=40,
            detectShadows=True
        )
        self.kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        self.kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))

        # Virtual counting line (Y-coordinate as fraction of frame height)
        self.count_line_y_ratio = 0.55
        self.counted_track_ids = set()
        self.total_counted = 0
        self.active_detections = 0
        self.estimated_occupancy_pct = 0.0

        # Centroid tracker memory: id -> (cx, cy)
        self.tracked_objects: Dict[int, Tuple[int, int]] = {}
        self.next_object_id = 1
        self.fps = 0.0

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Processes a single video frame, draws bounding boxes and counting lines,
        and returns the annotated frame and metrics dictionary.
        """
        t_start = time.time()
        h, w = frame.shape[:2]
        count_line_y = int(h * self.count_line_y_ratio)

        # 1. Preprocessing & Background Subtraction
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        fg_mask = self.bg_subtractor.apply(blurred)

        # Remove shadows (gray pixels in MOG2) and noise
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self.kernel_open)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, self.kernel_close)

        # 2. Contour Extraction
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        current_centroids = []
        total_veh_area = 0

        annotated = frame.copy()

        # Draw virtual counting line
        cv2.line(annotated, (0, count_line_y), (w, count_line_y), (0, 165, 255), 2)
        cv2.putText(
            annotated,
            "TRAFFIX AI Detection Line",
            (10, count_line_y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 165, 255),
            1
        )

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            total_veh_area += (bw * bh)

            cx = x + bw // 2
            cy = y + bh // 2
            current_centroids.append((cx, cy, (x, y, bw, bh)))

            # Vehicle classification based on bounding box dimensions
            if bw * bh > 14000 or bh > 90:
                vlabel = "Bus/Truck"
                color = (0, 0, 220) # Red
            elif bw * bh < 2200 and bw < 35:
                vlabel = "Motorcycle"
                color = (0, 220, 220) # Yellow
            else:
                vlabel = "Car"
                color = (255, 120, 0) # Blue/Cyan

            # Draw bounding box and label
            cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)
            cv2.circle(annotated, (cx, cy), 4, (0, 255, 0), -1)
            cv2.putText(
                annotated,
                f"{vlabel}",
                (x, max(15, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1
            )

        # 3. Virtual Line Crossing Detection
        for cx, cy, bbox in current_centroids:
            # Check if centroid is within tolerance band of counting line
            if abs(cy - count_line_y) < 12:
                # Match to closest tracked object or create new
                matched = False
                for oid, (px, py) in self.tracked_objects.items():
                    if abs(cx - px) < 40 and abs(cy - py) < 30:
                        matched = True
                        if oid not in self.counted_track_ids:
                            self.counted_track_ids.add(oid)
                            self.total_counted += 1
                        break
                if not matched:
                    new_id = self.next_object_id
                    self.next_object_id += 1
                    self.tracked_objects[new_id] = (cx, cy)
                    self.counted_track_ids.add(new_id)
                    self.total_counted += 1

        # Keep active centroid tracker bounded
        self.tracked_objects = {
            i: (cx, cy) for i, (cx, cy, _) in enumerate(current_centroids[:30])
        }

        # 4. Occupancy Estimation
        total_road_area = w * h * 0.7  # assuming 70% of frame is roadway
        self.estimated_occupancy_pct = min(100.0, round((total_veh_area / max(1, total_road_area)) * 100.0, 1))
        self.active_detections = len(current_centroids)

        t_end = time.time()
        self.fps = round(1.0 / max(0.001, t_end - t_start), 1)

        # 5. Overlay Stats Banner
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, 52), (15, 23, 42), -1)
        cv2.addWeighted(overlay, 0.85, annotated, 0.15, 0, annotated)

        cv2.putText(
            annotated,
            f"CAMERA-BASED DETECTION [OPENCV VISION] - NOT SUMO SIMULATION",
            (12, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (16, 185, 129),
            1
        )
        stats_str = f"Active: {self.active_detections} | Total Passed: {self.total_counted} | Occupancy: {self.estimated_occupancy_pct}% | FPS: {self.fps}"
        cv2.putText(
            annotated,
            stats_str,
            (12, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (248, 250, 252),
            1
        )

        metrics = {
            "mode": "OPENCV_CAMERA_DETECTION",
            "active_vehicles": self.active_detections,
            "total_passed_vehicles": self.total_counted,
            "lane_occupancy_pct": self.estimated_occupancy_pct,
            "fps": self.fps,
        }

        return annotated, metrics


class VideoStreamHandler:
    """
    Handles streaming frames from webcam, uploaded video, or procedural traffic generator.
    """

    def __init__(self):
        self.detector = CameraVehicleDetector()
        self.source_type = "synthetic"  # 'synthetic', 'webcam', or file path
        self.cap = None
        self.is_active = False
        self._lock = threading.Lock()
        self.current_metrics = {}

    def set_source(self, source_type: str, file_path: Optional[str] = None):
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None

            self.source_type = source_type
            if source_type == "webcam":
                self.cap = cv2.VideoCapture(0)
            elif source_type == "file" and file_path and os.path.isfile(file_path):
                self.cap = cv2.VideoCapture(file_path)
            else:
                self.source_type = "synthetic"
            self.detector = CameraVehicleDetector()

    def get_frame(self) -> Tuple[bytes, Dict[str, Any]]:
        """Reads, processes, and returns JPEG encoded frame bytes and metrics."""
        with self._lock:
            frame = None
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    # Loop video
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()

            if frame is None:
                frame = self._generate_synthetic_traffic_frame()

            annotated_frame, metrics = self.detector.process_frame(frame)
            self.current_metrics = metrics

            _, buffer = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return buffer.tobytes(), metrics

    def _generate_synthetic_traffic_frame(self) -> np.ndarray:
        """
        Generates a realistic procedural 3-lane highway camera frame with moving vehicles.
        Allows instant demonstration out-of-the-box without requiring a physical camera or video file.
        """
        w, h = 640, 360
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Draw Asphalt Roadway
        cv2.rectangle(frame, (60, 0), (w - 60, h), (45, 45, 50), -1)

        # Lane dividers
        t_sec = time.time()
        offset = int((t_sec * 80) % 40)
        for y in range(-40 + offset, h, 40):
            cv2.line(frame, (230, y), (230, y + 20), (220, 220, 220), 2)
            cv2.line(frame, (410, y), (410, y + 20), (220, 220, 220), 2)

        # Road boundaries
        cv2.line(frame, (60, 0), (60, h), (255, 255, 255), 3)
        cv2.line(frame, (w - 60, 0), (w - 60, h), (255, 255, 255), 3)

        # Generate moving synthetic vehicles
        vehicles_config = [
            # (lane_center_x, speed_px_per_sec, length, width, color, phase_offset)
            (145, 110, 50, 26, (180, 80, 40), 0.0),    # Lane 1 Car
            (145, 80, 85, 30, (40, 160, 40), 2.2),     # Lane 1 Bus
            (320, 130, 48, 24, (200, 190, 40), 1.1),   # Lane 2 Car
            (320, 100, 75, 30, (40, 40, 200), 3.5),    # Lane 2 Truck
            (495, 140, 30, 16, (30, 180, 220), 0.6),   # Lane 3 Motorcycle
            (495, 120, 48, 24, (160, 40, 180), 2.8),   # Lane 3 Car
        ]

        for lx, spd, vlen, vwid, col, poff in vehicles_config:
            vy = int(((t_sec + poff) * spd) % (h + 120)) - 60
            vx1 = lx - vwid // 2
            vy1 = vy
            vx2 = lx + vwid // 2
            vy2 = vy + vlen

            # Draw vehicle body
            cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), col, -1)
            cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (255, 255, 255), 1)

            # Headlights / taillights
            cv2.circle(frame, (vx1 + 4, vy2 - 3), 3, (0, 0, 255), -1)
            cv2.circle(frame, (vx2 - 4, vy2 - 3), 3, (0, 0, 255), -1)

        return frame


camera_stream = VideoStreamHandler()
