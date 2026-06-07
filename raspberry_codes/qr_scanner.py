import cv2
import json
import time


def parse_qr(raw):
    raw = raw.strip()

    try:
        parsed = json.loads(raw)

        if isinstance(parsed, dict):
            return parsed

        return {"name": str(parsed)}

    except Exception:
        return {"name": raw}


def scan_qr_once(camera_index=0, timeout_seconds=20):
    print(">>> QR Scanning...")

    cap = cv2.VideoCapture(camera_index)
    cap.set(3, 640)
    cap.set(4, 480)

    if not cap.isOpened():
        print(">>> Camera not opened")
        return {
            "success": False,
            "error": "Camera not opened"
        }

    detector = cv2.QRCodeDetector()

    # مهم: نعطي الكاميرا لحظات تجهز
    start = time.time()

    try:
        while True:
            # timeout
            if time.time() - start > timeout_seconds:
                print(">>> No QR detected")
                return {
                    "success": False,
                    "error": "No QR detected"
                }

            ret, frame = cap.read()

            if not ret:
                print(">>> No frame")
                continue

            data, bbox, _ = detector.detectAndDecode(frame)

            if data:
                raw = data.strip()
                print(">>> QR Found:", raw)

                parsed = parse_qr(raw)

                return {
                    "success": True,
                    "raw": raw,
                    "data": parsed
                }

    finally:
        cap.release()
