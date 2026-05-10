import cv2
import json
import time


def scan_qr_once(camera_index=0, timeout_seconds=10):
    cap = cv2.VideoCapture(camera_index)
    cap.set(3, 640)
    cap.set(4, 480)

    if not cap.isOpened():
        return {
            "success": False,
            "error": "Camera not opened"
        }

    detector = cv2.QRCodeDetector()
    start = time.time()

    try:
        while time.time() - start < timeout_seconds:
            ret, frame = cap.read()

            if not ret:
                continue

            data, bbox, _ = detector.detectAndDecode(frame)

            if data:
                raw = data.strip()

                try:
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        parsed = {"name": str(parsed)}
                except Exception:
                    parsed = {"name": raw}

                return {
                    "success": True,
                    "raw": raw,
                    "data": parsed
                }

        return {
            "success": False,
            "error": "No QR detected"
        }

    finally:
        cap.release()