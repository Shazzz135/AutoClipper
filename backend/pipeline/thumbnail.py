import cv2
import numpy as np
from pathlib import Path
from typing import Optional
from backend.core.state import state

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

class ThumbnailGenerator:
    def extract_most_expressive_thumbnail(self, video_path: Path, output_thumbnail_path: Path) -> bool:
        """
        Samples frames from the video, computes facial expression intensity (mouth & eye openness),
        or dynamic motion energy, and extracts the single most expressive frame as the video thumbnail.
        """
        state.add_col3_log("Analyzing frames for peak expression thumbnail...")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return False

        # Sample 15 frames distributed across the video
        sample_indices = np.linspace(0, total_frames - 1, min(15, total_frames), dtype=int)
        best_score = -1.0
        best_frame = None

        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            score = 0.0
            if HAS_FACE_RECOGNITION:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
                landmarks_list = face_recognition.face_landmarks(small_frame)
                if landmarks_list:
                    score = self._compute_expression_score(landmarks_list[0])
            else:
                # OpenCV fallback: compute edge/sharpness energy via Laplacian variance
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                score = cv2.Laplacian(gray, cv2.CV_64F).var()

            if score > best_score:
                best_score = score
                best_frame = frame
            elif best_frame is None:
                best_frame = frame

        cap.release()

        if best_frame is not None:
            cv2.imwrite(str(output_thumbnail_path), best_frame)
            state.add_col3_log(f"Extracted viral thumbnail (expression score: {best_score:.2f})")
            return True

        return False

    def _compute_expression_score(self, landmarks: dict) -> float:
        """
        Computes expression intensity score based on mouth aspect ratio (MAR) and eyebrow raise.
        """
        score = 0.0
        # Mouth aspect ratio
        if "top_lip" in landmarks and "bottom_lip" in landmarks:
            top_lip = np.array(landmarks["top_lip"])
            bottom_lip = np.array(landmarks["bottom_lip"])
            # Vertical mouth distance
            mouth_height = np.linalg.norm(np.mean(top_lip, axis=0) - np.mean(bottom_lip, axis=0))
            score += float(mouth_height) * 2.0

        # Eyebrow raise relative to eyes
        if "left_eyebrow" in landmarks and "left_eye" in landmarks:
            eyebrow = np.array(landmarks["left_eyebrow"])
            eye = np.array(landmarks["left_eye"])
            brow_dist = np.linalg.norm(np.mean(eyebrow, axis=0) - np.mean(eye, axis=0))
            score += float(brow_dist)

        return score

thumbnail_gen = ThumbnailGenerator()
