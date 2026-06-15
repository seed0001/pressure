"""
Remote Vision Client for Household Agent.
Run this script on the remote system with the webcam attached.
It performs local OpenCV vision processing and POSTs the structured state
to the main Household Agent server.

Usage:
  python remote_vision_client.py --server http://<agent-server-ip>:7437
"""

import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import cv2
import time
import numpy as np
import urllib.request
import urllib.parse
import json
import argparse

def main():
    parser = argparse.ArgumentParser(description="Remote Vision Client for Household Agent")
    parser.add_argument("--server", default="http://localhost:7437", help="URL of the agent server")
    parser.add_argument("--cam", type=int, default=0, help="Camera index to use")
    parser.add_argument("--fps", type=float, default=10.0, help="Target frames per second")
    args = parser.parse_args()

    server_url = args.server.rstrip("/") + "/api/vision_state"
    print(f"[Remote Vision] Connecting to agent server at: {server_url}")

    # Initialize video capture
    cap = None
    try:
        cap = cv2.VideoCapture(args.cam)
    except Exception as e:
        print(f"[Remote Vision] Error opening camera: {e}")

    if cap is None or not cap.isOpened():
        print(f"[Remote Vision] Error: Could not open camera on index {args.cam}.")
        return

    # Try setting resolution
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    except Exception:
        pass

    # Haar Cascade for face detection
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)

    prev_gray = None
    delay = 1.0 / args.fps
    print("[Remote Vision] Processing started. Press Ctrl+C to stop.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[Remote Vision] Warning: Failed to grab frame. Retrying in 1s...")
                send_state(server_url, {"camera_blocked": True})
                time.sleep(1.0)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 1. Brightness estimation
            brightness = np.mean(gray) / 255.0
            
            # 2. Camera blocked estimation (very dark and very little variance)
            variance = np.var(gray)
            camera_blocked = (brightness < 0.05 and variance < 10)
            
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
                
                novelty_score = motion_level  # Simple proxy
                if motion_level > 0.8:
                    scene_changed = True
                    
            prev_gray = gray
            
            # 4. Face Detection (CPU-friendly Haar Cascades)
            face_count = 0
            face_present = False
            person_present = (motion_level > 0.3)
            attention = False
            
            if not face_cascade.empty():
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                face_count = len(faces)
                face_present = face_count > 0
                person_present = face_present or person_present
                
                if face_present:
                    # If the largest face occupies a significant portion of the screen, assume attention
                    max_area = max(w*h for (x,y,w,h) in faces)
                    if max_area > (gray.shape[0] * gray.shape[1] * 0.05): # Face takes up > 5% of screen
                        attention = True

            state = {
                "person_present": person_present,
                "face_present": face_present,
                "face_count": face_count,
                "motion_level": round(float(motion_level), 3),
                "brightness_level": round(float(brightness), 3),
                "scene_changed": scene_changed,
                "camera_blocked": camera_blocked,
                "novelty_score": round(float(novelty_score), 3),
                "attention_detected": attention,
            }

            # Send state to agent server
            send_state(server_url, state)
            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[Remote Vision] Stopping client...")
    finally:
        cap.release()

def send_state(url, state):
    try:
        data = json.dumps(state).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            response.read()
    except Exception as e:
        print(f"[Remote Vision] Connection warning: Failed to send state: {e}")

if __name__ == "__main__":
    main()
