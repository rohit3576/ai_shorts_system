"""OpenCV focus estimation for vertical crops."""

from __future__ import annotations

import logging
from pathlib import Path
from statistics import median

logger = logging.getLogger(__name__)


class OpenCVFocusAnalyzer:
    """Estimate where the important horizontal action is in a clip."""

    def estimate_focus_x(self, video_path: Path, start_time: float, end_time: float) -> float:
        """Return a normalized horizontal focus point between 0 and 1."""

        try:
            import cv2
        except ImportError:
            logger.warning("OpenCV is not installed; using center crop")
            return 0.5

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return 0.5

        face_detector = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        centers: list[float] = []
        previous_gray = None
        samples = 12
        duration = max(0.1, end_time - start_time)

        for index in range(samples):
            timestamp = start_time + duration * (index / max(1, samples - 1))
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue

            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            if len(faces):
                x, _y, w, _h = max(faces, key=lambda box: box[2] * box[3])
                centers.append((x + w / 2) / width)
            elif previous_gray is not None:
                diff = cv2.absdiff(gray, previous_gray)
                _, threshold = cv2.threshold(diff, 28, 255, cv2.THRESH_BINARY)
                moments = cv2.moments(threshold)
                if moments["m00"]:
                    centers.append((moments["m10"] / moments["m00"]) / width)
            previous_gray = gray

        capture.release()
        if not centers:
            return 0.5
        return max(0.12, min(0.88, float(median(centers))))

