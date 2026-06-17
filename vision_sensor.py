import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import threading
import time

try:
    import cv2
    import numpy as np
except Exception as e:
    cv2 = None
    np = None
    _VISION_IMPORT_ERROR = str(e)
else:
    _VISION_IMPORT_ERROR = ""

_lock = threading.Lock()

# Global state dictionary exposing structured visual sensor data
_state = {
    "person_present": False,
    "face_present": False,
    "face_count": 0,
    "motion_level": 0.0,
    "brightness_level": 0.0,
    "scene_changed": False,
    "camera_blocked": False,
    "novelty_score": 0.0,
    "attention_detected": False,
    "camera_source": "none",
    "camera_error": "",
}

_thread = None
_running = False

_face_cascade = None
if cv2 is not None:
    try:
        _face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except Exception as e:
        print(f"[Vision] Error loading global face cascade: {e}")

_browser_prev_gray = None
_latest_frame_jpeg = None
_latest_frame_time = 0.0

def get_current_state() -> dict:
    """Thread-safe getter for the rest of the application."""
    _check_browser_timeout()
    with _lock:
        return dict(_state)

def get_status() -> dict:
    """Return vision state plus operational camera diagnostics."""
    _check_browser_timeout()
    with _lock:
        status = dict(_state)
        status["running"] = bool(_running)
        status["has_frame"] = _latest_frame_jpeg is not None
        status["frame_age_seconds"] = (
            round(time.time() - _latest_frame_time, 2)
            if _latest_frame_time else None
        )
        return status

def update_state(new_state: dict):
    """Update the visual state from an external source (e.g. remote camera script)."""
    global _latest_frame_time
    with _lock:
        for k, v in new_state.items():
            if k in _state:
                if isinstance(_state[k], bool):
                    _state[k] = bool(v)
                elif isinstance(_state[k], float):
                    _state[k] = round(float(v), 3)
                elif isinstance(_state[k], int):
                    _state[k] = int(v)
                else:
                    _state[k] = v
        _state["camera_source"] = str(new_state.get("camera_source", "remote"))
        _state["camera_error"] = ""
        _latest_frame_time = time.time()

def set_idle(source: str = "none", error: str = "") -> None:
    """Set camera operational status and clear active detection indicators."""
    global _running, _latest_frame_jpeg
    _running = False
    with _lock:
        _state.update({
            "person_present": False,
            "face_present": False,
            "face_count": 0,
            "motion_level": 0.0,
            "brightness_level": 0.0,
            "scene_changed": False,
            "camera_blocked": bool(error),
            "novelty_score": 0.0,
            "attention_detected": False,
            "camera_source": source,
            "camera_error": error,
        })
        _latest_frame_jpeg = None

def _check_browser_timeout() -> None:
    """Check if the browser camera has stopped sending frames (4-second timeout)."""
    global _latest_frame_jpeg
    with _lock:
        if _state.get("camera_source") == "browser":
            if time.time() - _latest_frame_time > 4.0:
                _state.update({
                    "person_present": False,
                    "face_present": False,
                    "face_count": 0,
                    "motion_level": 0.0,
                    "brightness_level": 0.0,
                    "scene_changed": False,
                    "camera_blocked": False,
                    "novelty_score": 0.0,
                    "attention_detected": False,
                    "camera_source": "none",
                    "camera_error": "",
                })
                _latest_frame_jpeg = None


def _vision_loop():
    global _state, _running, _latest_frame_time

    cap = None
    attempted = []
    backends = [
        ("default", None),
        ("dshow", getattr(cv2, "CAP_DSHOW", None)),
        ("msmf", getattr(cv2, "CAP_MSMF", None)),
    ]

    for backend_name, backend in backends:
        if cap is not None and cap.isOpened():
            break
        if backend_name in attempted:
            continue
        attempted.append(backend_name)
        for idx in range(5):
            try:
                temp_cap = cv2.VideoCapture(idx, backend) if backend is not None else cv2.VideoCapture(idx)
                if temp_cap.isOpened():
                    ret, frame = temp_cap.read()
                    if ret and frame is not None:
                        cap = temp_cap
                        print(f"[Vision] Opened local camera index {idx} using {backend_name}.")
                        break
                temp_cap.release()
            except Exception as e:
                print(f"[Vision] Exception opening camera {idx} via {backend_name}: {e}")

    if cap is None or not cap.isOpened():
        with _lock:
            _state["camera_blocked"] = True
            _state["camera_source"] = "none"
            _state["camera_error"] = "No local camera found via default, DirectShow, or Media Foundation"
        _running = False
        print("[Vision] No local camera found on main host. Ready for remote/browser camera feeds.")
        return
        
    # Use shared Haar cascade
    face_cascade = _face_cascade
    
    prev_gray = None
    
    # Optional: Lower resolution for faster processing
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    except Exception as e:
        print(f"[Vision] Warning: Could not set camera resolution: {e}")
    
    print("[Vision] Camera initialized. Starting continuous perception loop.")
    
    while _running:
        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                with _lock:
                    _state["camera_blocked"] = True
                time.sleep(1.0)
                continue
            
            # Cache the latest frame as JPEG
            try:
                _, jpeg_bytes = cv2.imencode('.jpg', frame)
                if _:
                    global _latest_frame_jpeg
                    _latest_frame_jpeg = jpeg_bytes.tobytes()
                    _latest_frame_time = time.time()
            except Exception as e:
                print(f"[Vision] Exception caching local frame: {e}")
                
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 1. Brightness estimation
            brightness = np.mean(gray) / 255.0
            
            # 2. Camera blocked estimation (very dark and very little variance)
            variance = np.var(gray)
            camera_blocked = (brightness < 0.02 and variance < 3)
            
            # 3. Motion detection
            motion_level = 0.0
            scene_changed = False
            novelty_score = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                motion_pixels = cv2.countNonZero(thresh)
                total_pixels = gray.shape[0] * gray.shape[1]
                motion_level = min(1.0, motion_pixels / (total_pixels * 0.1)) # Normalize: 10% pixels moving = 1.0 motion
                
                novelty_score = motion_level  # Simple proxy for now
                if motion_level > 0.8:
                    scene_changed = True
                    
            prev_gray = gray
            
            # 4. Face Detection (throttled to save CPU - only every few frames or if there's motion)
            face_count = 0
            face_present = False
            person_present = (motion_level > 0.3)
            attention = False
            
            if face_cascade is not None:
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                face_count = len(faces)
                face_present = face_count > 0
                person_present = face_present or person_present
                
                if face_present:
                    # If the largest face occupies a significant portion of the screen, assume attention
                    max_area = max(w*h for (x,y,w,h) in faces)
                    if max_area > (gray.shape[0] * gray.shape[1] * 0.05): # Face takes up > 5% of screen
                        attention = True
                        
            with _lock:
                _state.update({
                    "person_present": bool(person_present),
                    "face_present": bool(face_present),
                    "face_count": int(face_count),
                    "motion_level": round(float(motion_level), 3),
                    "brightness_level": round(float(brightness), 3),
                    "scene_changed": bool(scene_changed),
                    "camera_blocked": bool(camera_blocked),
                    "novelty_score": round(float(novelty_score), 3),
                    "attention_detected": bool(attention),
                    "camera_source": "local",
                    "camera_error": "",
                })
        except Exception as e:
            with _lock:
                _state["camera_error"] = str(e)
            print(f"[Vision] Exception in vision loop: {e}")
            time.sleep(1.0)
            
        # ~10 FPS is plenty for ambient perception and keeps CPU usage low
        time.sleep(0.1)
        
    try:
        cap.release()
    except Exception as e:
        print(f"[Vision] Exception releasing camera: {e}")
    finally:
        _running = False

def start():
    """Start the background vision sensor thread."""
    global _thread, _running
    if _running:
        return
    if cv2 is None or np is None:
        set_idle("none", f"OpenCV unavailable: {_VISION_IMPORT_ERROR}")
        print(f"[Vision] OpenCV unavailable; local camera disabled: {_VISION_IMPORT_ERROR}")
        return
    _running = True
    _thread = threading.Thread(target=_vision_loop, daemon=True, name="VisionSensorThread")
    _thread.start()

def stop():
    """Stop the background vision sensor thread."""
    global _running
    _running = False
    if _thread:
        _thread.join()

def process_frame(frame) -> dict:
    """Process a single frame from the web browser. Updates the global visual state."""
    global _browser_prev_gray, _latest_frame_jpeg, _latest_frame_time, _state
    if frame is None:
        return get_current_state()
    if cv2 is None or np is None:
        set_idle("browser", f"OpenCV unavailable: {_VISION_IMPORT_ERROR}")
        return get_current_state()
    
    # Cache the latest browser frame as JPEG
    try:
        _, jpeg_bytes = cv2.imencode('.jpg', frame)
        if _:
            _latest_frame_jpeg = jpeg_bytes.tobytes()
            _latest_frame_time = time.time()
    except Exception as e:
        print(f"[Vision] Exception caching browser frame: {e}")
    try:
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # 1. Brightness estimation
        brightness = np.mean(gray) / 255.0

        # 2. Camera blocked estimation (very dark and very little variance)
        variance = np.var(gray)
        camera_blocked = (brightness < 0.02 and variance < 3)

        # 3. Motion detection
        motion_level = 0.0
        scene_changed = False
        novelty_score = 0.0
        if _browser_prev_gray is not None and _browser_prev_gray.shape == gray.shape:
            diff = cv2.absdiff(_browser_prev_gray, gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            motion_pixels = cv2.countNonZero(thresh)
            total_pixels = gray.shape[0] * gray.shape[1]
            motion_level = min(1.0, motion_pixels / (total_pixels * 0.1)) # Normalize: 10% pixels moving = 1.0 motion
            
            novelty_score = motion_level
            if motion_level > 0.8:
                scene_changed = True

        _browser_prev_gray = gray

        # 4. Face Detection
        face_count = 0
        face_present = False
        person_present = (motion_level > 0.3)
        attention = False

        if _face_cascade is not None and not _face_cascade.empty():
            faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            face_count = len(faces)
            face_present = face_count > 0
            person_present = face_present or person_present

            if face_present:
                # If the largest face occupies a significant portion of the screen, assume attention
                max_area = max(w*h for (x,y,w,h) in faces)
                if max_area > (gray.shape[0] * gray.shape[1] * 0.05): # Face takes up > 5% of screen
                    attention = True

        with _lock:
            _state.update({
                "person_present": bool(person_present),
                "face_present": bool(face_present),
                "face_count": int(face_count),
                "motion_level": round(float(motion_level), 3),
                "brightness_level": round(float(brightness), 3),
                "scene_changed": bool(scene_changed),
                "camera_blocked": bool(camera_blocked),
                "novelty_score": round(float(novelty_score), 3),
                "attention_detected": bool(attention),
                "camera_source": "browser",
                "camera_error": "",
            })
    except Exception as e:
        with _lock:
            _state["camera_error"] = str(e)
        print(f"[Vision] Exception in browser process_frame: {e}")

    return get_current_state()

def get_latest_frame() -> bytes:
    """Retrieve the raw bytes of the latest processed JPEG frame."""
    _check_browser_timeout()
    global _latest_frame_jpeg
    return _latest_frame_jpeg
