"""Local OpenCV fingertip tracker for the EduVerse webcam drawing studio."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cv2
import numpy as np

HOST = "127.0.0.1"
PORT = 4174
GESTURE_SAMPLES: list[dict] = []


def find_pointer(jpeg: bytes) -> dict:
    encoded = np.frombuffer(jpeg, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        return {"detected": False}
    # Mirror to match the mirrored webcam preview in the browser.
    frame = cv2.flip(frame, 1)
    height, width = frame.shape[:2]
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
    mask = cv2.GaussianBlur(mask, (7, 7), 0)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"detected": False}
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < max(700, width * height * 0.003) or area > width * height * 0.45:
        return {"detected": False}

    # Convexity defects give likely finger tips; top-most contour point is a fallback.
    candidates = []
    valid_defects = 0
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.006 * perimeter, True)
    hull = cv2.convexHull(approx, returnPoints=False)
    if hull is not None and len(hull) > 3 and len(approx) > 3:
        defects = cv2.convexityDefects(approx, hull)
        if defects is not None:
            for row in defects[:, 0]:
                start, end, far, depth = (approx[row[0]][0], approx[row[1]][0], approx[row[2]][0], row[3] / 256.0)
                if depth < 10:
                    continue
                a = np.linalg.norm(start - far)
                b = np.linalg.norm(end - far)
                c = np.linalg.norm(start - end)
                if a * b == 0:
                    continue
                angle = np.degrees(np.arccos(np.clip((a*a + b*b - c*c) / (2*a*b), -1, 1)))
                if angle < 78:
                    valid_defects += 1
                    candidates.extend([start, end])
    if candidates:
        tip = min(candidates, key=lambda point: point[1])
    else:
        tip = contour[contour[:, :, 1].argmin()][0]
    x, y = int(tip[0]), int(tip[1])
    x0, y0, box_w, box_h = cv2.boundingRect(contour)
    aspect = box_w / max(1, box_h)
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = area / max(1, hull_area)
    fingers = min(5, valid_defects + 1)
    hint = "open_hand" if fingers >= 4 else "two_fingers" if fingers == 2 else "fist" if valid_defects == 0 and aspect > 0.78 else "one_finger" if fingers == 1 else "uncertain"
    features = [round(fingers / 5, 4), round(min(2, aspect) / 2, 4), round(solidity, 4), round(min(4, valid_defects) / 4, 4)]
    return {"detected": True, "x": round(x / max(1, width), 5), "y": round(y / max(1, height), 5), "confidence": round(min(1.0, area / (width * height * 0.04)), 2), "fingerCountEstimate": fingers, "gestureHint": hint, "features": features}



def analyze_color(jpeg: bytes) -> dict:
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not read this image")
    h, w = frame.shape[:2]
    crop = frame[int(h * .35):int(h * .65), int(w * .35):int(w * .65)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue, sat, val = [float(v) for v in np.median(hsv.reshape(-1, 3), axis=0)]
    if val < 55:
        label = "black"
    elif sat < 42:
        label = "white" if val > 205 else "gray"
    elif hue < 10 or hue >= 170:
        label = "red"
    elif hue < 22:
        label = "orange"
    elif hue < 35:
        label = "yellow"
    elif hue < 85:
        label = "green"
    elif hue < 132:
        label = "blue"
    else:
        label = "purple"
    return {"color": label, "confidence": round(min(1.0, sat / 140), 2), "method": "median HSV from the centre of the camera frame"}


def nearest_gesture(features: list[float]) -> dict:
    if len(GESTURE_SAMPLES) < 2 or len({s["label"] for s in GESTURE_SAMPLES}) < 2:
        return {"trained": False, "message": "Collect examples from at least two labels first."}
    distances = []
    for sample in GESTURE_SAMPLES:
        dist = sum((float(a) - float(b)) ** 2 for a, b in zip(features, sample["features"])) ** .5
        distances.append((dist, sample["label"]))
    nearest = sorted(distances)[:3]
    scores: dict[str, float] = {}
    for dist, label in nearest:
        scores[label] = scores.get(label, 0) + 1 / max(.02, dist)
    label = max(scores, key=scores.get)
    total = sum(scores.values())
    return {"trained": True, "label": label, "confidence": round(scores[label] / total, 2), "examples": len(GESTURE_SAMPLES)}


FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
BODY_HOG = cv2.HOGDescriptor()
BODY_HOG.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def perceive(jpeg: bytes) -> dict:
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not read this camera frame")
    h, w = frame.shape[:2]
    factor = min(1.0, 480 / max(h, w))
    small = cv2.resize(frame, (int(w * factor), int(h * factor))) if factor < 1 else frame
    small = cv2.flip(small, 1)
    gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    faces = FACE_CASCADE.detectMultiScale(gray, 1.1, 4, minSize=(36, 36)) if not FACE_CASCADE.empty() else []
    face_rows = []
    gaze = "unknown"
    for (x, y, fw, fh) in faces[:4]:
        eye_area = gray[y:y + int(fh * .62), x:x + fw]
        eyes = EYE_CASCADE.detectMultiScale(eye_area, 1.1, 4, minSize=(8, 8)) if not EYE_CASCADE.empty() else []
        eye_rows = sorted([(int(x + ex + ew / 2), int(y + ey + eh / 2), int(ex), int(ey), int(ew), int(eh)) for ex, ey, ew, eh in eyes], key=lambda p: p[0])[:2]
        centers = [(row[0], row[1]) for row in eye_rows]
        face_rows.append({"box": [int(x / factor), int(y / factor), int(fw / factor), int(fh / factor)], "eyes": [[int(ex / factor), int(ey / factor)] for ex, ey in centers]})
        eye_positions = []
        for _, _, ex, ey, ew, eh in eye_rows:
            eye_crop = eye_area[max(0, ey):ey + eh, max(0, ex):ex + ew]
            if eye_crop.size == 0:
                continue
            inner = eye_crop[int(eh * .2):max(int(eh * .8), 1), int(ew * .2):max(int(ew * .8), 1)]
            if inner.size == 0:
                continue
            threshold = np.percentile(inner, 22)
            darkness = np.maximum(0, threshold - inner.astype(np.float32))
            total = float(darkness.sum())
            if total > 0:
                col = float((darkness * np.arange(inner.shape[1])[None, :]).sum() / total) / max(1, inner.shape[1] - 1)
                eye_positions.append(col)
        if len(eye_positions) >= 2:
            pupil_hint = float(np.mean(eye_positions))
            gaze = "left" if pupil_hint < .38 else "right" if pupil_hint > .62 else "center"
    pedestrians = []
    if min(small.shape[:2]) >= 120:
        boxes, weights = BODY_HOG.detectMultiScale(small, winStride=(8, 8), padding=(4, 4), scale=1.08)
        for (x, y, bw, bh), weight in zip(boxes[:4], weights[:4]):
            pedestrians.append({"box": [int(x / factor), int(y / factor), int(bw / factor), int(bh / factor)], "confidence": round(float(weight), 2)})
    return {"faces": face_rows, "faceCount": len(face_rows), "eyeRegions": sum(len(f["eyes"]) for f in face_rows), "gazeHint": gaze, "people": pedestrians}



def stylize_sketch(jpeg: bytes, style: str = "tutorial") -> bytes:
    """Apply one of the attached webcam-sketch Canny pipelines to a frame."""
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not read this camera frame")
    if style == "classic":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 10, 80)
        _, mask = cv2.threshold(edges, 50, 255, cv2.THRESH_BINARY_INV)
    else:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 60)
        _, mask = cv2.threshold(edges, 240, 255, cv2.THRESH_BINARY_INV)
    # Match the horizontally mirrored browser camera preview.
    mask = cv2.flip(mask, 1)
    ok, encoded = cv2.imencode(".jpg", mask, [cv2.IMWRITE_JPEG_QUALITY, 86])
    if not ok:
        raise ValueError("Could not render the sketch frame")
    return encoded.tobytes()


def clean_board(jpeg: bytes) -> bytes:
    """Return a locally enhanced high-contrast board preview; this is not OCR."""
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not read this image")
    if frame.shape[1] > 1400:
        scale = 1400 / frame.shape[1]
        frame = cv2.resize(frame, (1400, int(frame.shape[0] * scale)))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    cleaned = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    ok, encoded = cv2.imencode(".jpg", cleaned, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Could not process this image")
    return encoded.tobytes()


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps({"ok": True, "service": "eduverse-opencv-labs", "capabilities": ["fingertip-contour", "gesture-hint-experimental", "sample-nearest-neighbor-classifier", "live-canny-sketch-modes", "center-color-analysis", "face-eye-region-detection", "person-framing-hog", "board-image-cleanup-no-ocr"]}).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route not in ("/track", "/scan", "/stylize", "/analyze", "/learn", "/classify", "/perceive", "/reset"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 8_000_000:
            self.send_error(413)
            return
        try:
            raw = self.rfile.read(length)
            if route == "/scan":
                body = clean_board(raw)
                content_type = "image/jpeg"
            elif route == "/stylize":
                from urllib.parse import parse_qs
                style = parse_qs(self.path.partition("?")[2]).get("mode", ["tutorial"])[0]
                body = stylize_sketch(raw, style)
                content_type = "image/jpeg"
            elif route == "/analyze":
                body = json.dumps(analyze_color(raw)).encode()
                content_type = "application/json"
            elif route == "/perceive":
                body = json.dumps(perceive(raw)).encode()
                content_type = "application/json"
            elif route in ("/learn", "/classify", "/reset"):
                data = json.loads(raw)
                if route == "/reset":
                    GESTURE_SAMPLES.clear()
                    body = json.dumps({"reset": True}).encode()
                elif route == "/learn":
                    label = str(data.get("label", ""))[:40].strip()
                    features = data.get("features", [])
                    if not label or len(features) != 4:
                        raise ValueError("A label and current hand features are required")
                    GESTURE_SAMPLES.append({"label": label, "features": [float(v) for v in features]})
                    body = json.dumps({"saved": True, "label": label, "count": sum(s["label"] == label for s in GESTURE_SAMPLES), "total": len(GESTURE_SAMPLES)}).encode()
                else:
                    body = json.dumps(nearest_gesture(data.get("features", []))).encode()
                content_type = "application/json"
            else:
                body = json.dumps(find_pointer(raw)).encode()
                content_type = "application/json"
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode()
            self.send_response(400)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print("[opencv] " + fmt % args)


if __name__ == "__main__":
    print(f"EduVerse OpenCV tracker listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
