import cv2
import numpy as np
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from backend.core.config import settings
from backend.core.state import state

# Path to YuNet ONNX deep learning face detector model
YUNET_MODEL_PATH = settings.BASE_DIR / "backend" / "models" / "face_detection_yunet.onnx"

class FacecamCropper:
    def __init__(self):
        self.target_face_w = settings.OUTPUT_WIDTH # 1080
        self.target_face_h = int(settings.OUTPUT_HEIGHT * settings.LAYOUT_FACECAM_RATIO) # 768
        self.target_game_w = settings.OUTPUT_WIDTH # 1080
        self.target_game_h = int(settings.OUTPUT_HEIGHT * settings.LAYOUT_GAMEPLAY_RATIO) # 1152

        # Initialize YuNet Deep Learning Face Detector
        self.detector = None
        if YUNET_MODEL_PATH.exists():
            try:
                self.detector = cv2.FaceDetectorYN.create(
                    str(YUNET_MODEL_PATH),
                    "",
                    (1280, 720),
                    0.35, # Score threshold
                    0.3   # NMS threshold
                )
            except Exception as e:
                print("YuNet init error:", e)

    def analyze_and_compute_crops(self, video_path: Path) -> Dict[str, str]:
        """
        Samples keyframes from the video, finds the facecam box,
        and computes FFmpeg crop/scale filter strings for 40/60 vertical composition.
        Also exports preview crop images for the dashboard.
        """
        state.col2_status = "DETECTING"
        state.add_col2_log(f"Analyzing keyframes from candidate clip: {video_path.name}")

        orig_w, orig_h = 1280, 720
        temp_frame_path = settings.BUFFER_DIR / "temp_detect_frame.jpg"

        # Use FFmpeg to reliably extract test frames across the video
        detected_boxes = []
        best_frame = None
        best_conf = 0.0

        for seek_sec in [1, 2, 4]:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(seek_sec),
                "-i", str(video_path),
                "-frames:v", "1",
                "-update", "1",
                str(temp_frame_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not temp_frame_path.exists():
                continue

            frame = cv2.imread(str(temp_frame_path))
            if frame is None:
                continue

            orig_h, orig_w, _ = frame.shape
            face_result = self._detect_face_in_frame(frame)

            if face_result:
                left, top, fw, fh, conf = face_result
                cam_box, rule_name = self._auto_expand_facecam_box(frame, left, top, fw, fh, orig_w, orig_h)
                detected_boxes.append((cam_box, conf, fh, rule_name))
                if conf > best_conf:
                    best_conf = conf
                    best_frame = frame.copy()

        # Clean up temp detect frame
        if temp_frame_path.exists():
            try:
                temp_frame_path.unlink()
            except Exception:
                pass

        if detected_boxes:
            # Pick the highest confidence detected box
            detected_boxes.sort(key=lambda x: x[1], reverse=True)
            box, conf, fh, rule_name = detected_boxes[0]

            state.current_facecam_box = box
            state.last_known_facecam = box
            state.using_fallback = False
            state.edge_confidence = float(conf)
            state.col2_status = "LOCKED"
            state.facecam_rule_applied = rule_name
            state.add_col2_log(f"Facecam locked: {rule_name} at ({box['x']}, {box['y']}), size {box['w']}x{box['h']} (conf: {conf:.2f})")
        else:
            # Kai / Jynxzi not visible in sampled frames -> use last known position if available
            if state.last_known_facecam:
                box = state.last_known_facecam
                state.current_facecam_box = box
                state.using_fallback = True
                state.edge_confidence = 0.70
                state.col2_status = "FALLBACK_LOCKED"
                state.add_col2_log(f"No face detected in frames; using last known box: ({box['x']}, {box['y']})")
            else:
                state.using_fallback = True
                state.col2_status = "DEFAULT_CENTER"
                state.add_col2_log("No face detected. Using bottom-left facecam fallback.")
                # Bottom-left facecam default (common for streamers like Jynxzi)
                box = {
                    'x': int(orig_w * 0.05),
                    'y': int(orig_h * 0.55),
                    'w': int(orig_w * 0.32),
                    'h': int(orig_h * 0.40)
                }

        # Generate crop filters
        filter_data = self._generate_filter_complex(box, orig_w, orig_h)

        # Generate preview images for the dashboard
        if best_frame is not None:
            self._save_crop_previews(best_frame, box, filter_data["game_crop"])

        state.col2_status = "OK"
        return filter_data

    def _detect_face_in_frame(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int, float]]:
        """Detects primary face using YuNet ONNX, returning (left, top, width, height, confidence)."""
        if self.detector is None:
            return None

        h, w, _ = frame.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)

        if faces is not None and len(faces) > 0:
            # Pick highest confidence face
            best_face = max(faces, key=lambda f: f[-1])
            left, top, fw, fh = int(best_face[0]), int(best_face[1]), int(best_face[2]), int(best_face[3])
            conf = float(best_face[-1])
            return left, top, fw, fh, conf

        return None

    def _detect_webcam_box(self, frame: np.ndarray, fx: int, fy: int, fw: int, fh: int, orig_w: int, orig_h: int) -> Tuple[bool, Optional[Dict[str, int]]]:
        """
        Detects whether the facecam has an enclosed webcam overlay box with a room background
        vs. a transparent/chroma-key cutout directly over the game.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 120)

        cx = fx + fw // 2
        cy = fy + fh // 2

        # Check standard corner / border positions
        is_left = cx < orig_w * 0.45
        is_right = cx > orig_w * 0.55
        is_bottom = cy > orig_h * 0.45
        is_top = cy < orig_h * 0.55

        min_line = int(fh * 0.6)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=45, minLineLength=min_line, maxLineGap=15)

        cam_x1, cam_y1, cam_x2, cam_y2 = None, None, None, None

        if lines is not None:
            v_lines = []
            h_lines = []
            for l in lines:
                x1, y1, x2, y2 = l.flatten()
                if abs(x1 - x2) <= 3:
                    v_lines.append(((x1 + x2) // 2, min(y1, y2), max(y1, y2)))
                elif abs(y1 - y2) <= 3:
                    h_lines.append(((y1 + y2) // 2, min(x1, x2), max(x1, x2)))

            # Corner-anchored webcam detection
            if is_left and is_bottom:
                cam_x1 = 0
                cam_y2 = orig_h
                r_cands = [x for x, y1, y2 in v_lines if (fx + fw) < x <= min(orig_w * 0.55, fx + int(fw * 4.0)) and y1 <= cy and y2 >= (fy - 20)]
                if r_cands:
                    cam_x2 = max(r_cands)
                t_cands = [y for y, x1, x2 in h_lines if max(0, fy - int(fh * 3.0)) <= y < fy and x1 <= (cx + 60) and x2 >= (cx - 60)]
                if t_cands:
                    cam_y1 = min(t_cands)
            elif is_right and is_bottom:
                cam_x2 = orig_w
                cam_y2 = orig_h
                l_cands = [x for x, y1, y2 in v_lines if max(orig_w * 0.45, fx - int(fw * 4.0)) <= x < fx and y1 <= cy and y2 >= (fy - 20)]
                if l_cands:
                    cam_x1 = min(l_cands)
                t_cands = [y for y, x1, x2 in h_lines if max(0, fy - int(fh * 3.0)) <= y < fy and x1 <= (cx + 60) and x2 >= (cx - 60)]
                if t_cands:
                    cam_y1 = min(t_cands)
            elif is_left and is_top:
                cam_x1 = 0
                cam_y1 = 0
                r_cands = [x for x, y1, y2 in v_lines if (fx + fw) < x <= min(orig_w * 0.55, fx + int(fw * 4.0)) and y1 <= (cy + 20) and y2 >= cy]
                if r_cands:
                    cam_x2 = max(r_cands)
                b_cands = [y for y, x1, x2 in h_lines if (fy + fh) < y <= min(orig_h * 0.6, fy + int(fh * 3.0)) and x1 <= (cx + 60) and x2 >= (cx - 60)]
                if b_cands:
                    cam_y2 = max(b_cands)
            elif is_right and is_top:
                cam_x2 = orig_w
                cam_y1 = 0
                l_cands = [x for x, y1, y2 in v_lines if max(orig_w * 0.45, fx - int(fw * 4.0)) <= x < fx and y1 <= (cy + 20) and y2 >= cy]
                if l_cands:
                    cam_x1 = min(l_cands)
                b_cands = [y for y, x1, x2 in h_lines if (fy + fh) < y <= min(orig_h * 0.6, fy + int(fh * 3.0)) and x1 <= (cx + 60) and x2 >= (cx - 60)]
                if b_cands:
                    cam_y2 = max(b_cands)

        # If borders were found, we have an identified webcam box
        if (cam_x1 is not None and cam_x2 is not None) or (cam_y1 is not None and cam_y2 is not None):
            if is_left and is_bottom:
                cam_x1 = 0 if cam_x1 is None else max(0, cam_x1)
                cam_y2 = orig_h if cam_y2 is None else min(orig_h, cam_y2)
                cam_x2 = min(int(orig_w * 0.45), int(fx + fw * 3.4)) if cam_x2 is None else min(orig_w, cam_x2)
                cam_y1 = max(0, int(fy - fh * 1.3)) if cam_y1 is None else max(0, cam_y1)
            elif is_right and is_bottom:
                cam_x2 = orig_w if cam_x2 is None else min(orig_w, cam_x2)
                cam_y2 = orig_h if cam_y2 is None else min(orig_h, cam_y2)
                cam_x1 = max(int(orig_w * 0.55), int(fx - fw * 2.4)) if cam_x1 is None else max(0, cam_x1)
                cam_y1 = max(0, int(fy - fh * 1.3)) if cam_y1 is None else max(0, cam_y1)
            elif is_left and is_top:
                cam_x1 = 0 if cam_x1 is None else max(0, cam_x1)
                cam_y1 = 0 if cam_y1 is None else max(0, cam_y1)
                cam_x2 = min(int(orig_w * 0.45), int(fx + fw * 3.4)) if cam_x2 is None else min(orig_w, cam_x2)
                cam_y2 = min(int(orig_h * 0.55), int(fy + fh * 2.3)) if cam_y2 is None else min(orig_h, cam_y2)
            elif is_right and is_top:
                cam_x2 = orig_w if cam_x2 is None else min(orig_w, cam_x2)
                cam_y1 = 0 if cam_y1 is None else max(0, cam_y1)
                cam_x1 = max(int(orig_w * 0.55), int(fx - fw * 2.4)) if cam_x1 is None else max(0, cam_x1)
                cam_y2 = min(int(orig_h * 0.55), int(fy + fh * 2.3)) if cam_y2 is None else min(orig_h, cam_y2)
            else:
                cam_x1 = 0 if cam_x1 is None else max(0, cam_x1)
                cam_y1 = 0 if cam_y1 is None else max(0, cam_y1)
                cam_x2 = orig_w if cam_x2 is None else min(orig_w, cam_x2)
                cam_y2 = orig_h if cam_y2 is None else min(orig_h, cam_y2)

            box = {
                'x': int(cam_x1),
                'y': int(cam_y1),
                'w': int(cam_x2 - cam_x1),
                'h': int(cam_y2 - cam_y1)
            }
            return True, box

        # If streamer is anchored in bottom-left or bottom-right corner (standard setup like Jynxzi)
        if (is_left or is_right) and is_bottom:
            box = {
                'x': 0 if is_left else int(max(0, fx - fw * 1.5)),
                'y': max(0, int(fy - fh * 1.2)),
                'w': min(int(orig_w * 0.40), int(fx + fw * 3.2)) if is_left else int(orig_w - max(0, fx - fw * 1.5)),
                'h': orig_h - max(0, int(fy - fh * 1.2))
            }
            return True, box

        return False, None

    def _compute_rule1_box_with_background(self, cam_box: Dict[str, int], fx: int, fy: int, fw: int, fh: int, orig_w: int, orig_h: int) -> Dict[str, int]:
        """
        Rule 1 (Primary): Facecam with border/background.
        Scales the facecam section so that it measures just over 1080x768.
        Takes a 1080:768 aspect-ratio crop INSIDE the webcam box (zero gameplay bleed)
        centered around the streamer's face, so when upscaled, the entire webcam box
        fills and measures just over the 1080x768 slot edge-to-edge.
        """
        target_aspect = self.target_face_w / self.target_face_h  # 1080 / 768 = 1.40625

        cw = max(cam_box['w'], 1)
        ch = max(cam_box['h'], 1)
        cam_x = cam_box['x']
        cam_y = cam_box['y']

        fcx = fx + fw // 2
        fcy = fy + fh // 2

        cam_aspect = cw / ch
        # 4% overscan so the webcam box measures just over 1080x768 and eliminates edge borders
        overscan = 0.96

        if cam_aspect < target_aspect:
            # Webcam is squarer/taller than 1.40625: fit width inside webcam, crop height
            crop_w = int(cw * overscan)
            crop_h = int(crop_w / target_aspect)
        else:
            # Webcam is wider than 1.40625: fit height inside webcam, crop width
            crop_h = int(ch * overscan)
            crop_w = int(crop_h * target_aspect)

        # Center horizontally on face while keeping crop strictly within webcam box [cam_x, cam_x + cw]
        if cw > crop_w:
            crop_x = max(cam_x, min(fcx - crop_w // 2, cam_x + cw - crop_w))
        else:
            crop_x = max(0, min(cam_x, orig_w - crop_w))

        # Center vertically on face with natural headroom (~44% above face center)
        if ch > crop_h:
            ideal_y = fcy - int(crop_h * 0.44)
            crop_y = max(cam_y, min(ideal_y, cam_y + ch - crop_h))
        else:
            crop_y = max(0, min(cam_y, orig_h - crop_h))

        # Clamp safely within canvas
        crop_x = max(0, min(crop_x, orig_w - crop_w))
        crop_y = max(0, min(crop_y, orig_h - crop_h))

        # Even coordinates for FFmpeg
        w = crop_w - (crop_w % 2)
        h = crop_h - (crop_h % 2)
        x = crop_x - (crop_x % 2)
        y = crop_y - (crop_y % 2)

        return {'x': x, 'y': y, 'w': w, 'h': h}

    def _compute_rule2_no_background(self, fx: int, fy: int, fw: int, fh: int, orig_w: int, orig_h: int) -> Dict[str, int]:
        """
        Rule 2 (Secondary): No background / no border behind the face (cutout / green screen).
        Sizes the person's face to 50% of the height of the 40% screen (~384px tall)
        and centers the face in the screen.
        """
        target_aspect = self.target_face_w / self.target_face_h  # 1080 / 768 = 1.40625

        # In 768px window, face will be exactly 50% = 384px tall:
        # fh * (768 / crop_h) = 384 => crop_h = 2 * fh
        crop_h = int(fh / 0.50)
        crop_w = int(crop_h * target_aspect)

        if crop_h > orig_h:
            crop_h = orig_h
            crop_w = int(crop_h * target_aspect)
        if crop_w > orig_w:
            crop_w = orig_w
            crop_h = int(crop_w / target_aspect)

        # Center face in the facecam window
        cx = fx + fw // 2
        cy = fy + fh // 2

        crop_x = cx - crop_w // 2
        crop_y = cy - crop_h // 2

        crop_x = max(0, min(crop_x, orig_w - crop_w))
        crop_y = max(0, min(crop_y, orig_h - crop_h))

        # Even coordinates for FFmpeg
        w = crop_w - (crop_w % 2)
        h = crop_h - (crop_h % 2)
        x = crop_x - (crop_x % 2)
        y = crop_y - (crop_y % 2)

        return {'x': x, 'y': y, 'w': w, 'h': h}

    def _auto_expand_facecam_box(self, frame, fx, fy, fw, fh, orig_w, orig_h) -> Tuple[Dict[str, int], str]:
        """
        Primary is a facecam with a border/background, scaling it so its size measures just over 1080x768.
        Only if there is no border or background (e.g. green screen / cutout) do we size the face to 50% of the 40% screen (384px).
        """
        mode = getattr(state, 'facecam_mode', 'AUTO').upper()

        if mode == "BACKGROUND":
            use_primary = True
            _, detected_cam = self._detect_webcam_box(frame, fx, fy, fw, fh, orig_w, orig_h)
        elif mode == "NO_BACKGROUND":
            use_primary = False
            detected_cam = None
        else:  # AUTO
            # Primary check: Detect facecam with border/background
            has_bg, detected_cam = self._detect_webcam_box(frame, fx, fy, fw, fh, orig_w, orig_h)
            use_primary = has_bg

        state.facecam_has_background = use_primary

        if use_primary:
            cam_box = detected_cam if detected_cam else {
                'x': max(0, fx - int(fw * 0.8)),
                'y': max(0, fy - int(fh * 0.8)),
                'w': min(orig_w - max(0, fx - int(fw * 0.8)), int(fw * 3.2)),
                'h': min(orig_h - max(0, fy - int(fh * 0.8)), int(fh * 2.8))
            }
            box = self._compute_rule1_box_with_background(cam_box, fx, fy, fw, fh, orig_w, orig_h)
            rule_applied = "PRIMARY: WEBCAM BORDER/BG (1080x768+)"
        else:
            box = self._compute_rule2_no_background(fx, fy, fw, fh, orig_w, orig_h)
            rule_applied = "SECONDARY: 50% FACE CUTOUT (384px)"

        state.facecam_rule_applied = rule_applied
        return box, rule_applied

        state.facecam_rule_applied = rule_applied
        return box, rule_applied

    def _generate_filter_complex(self, face_box: Dict[str, int], orig_w: int, orig_h: int) -> Dict[str, str]:
        """
        Generates FFmpeg filter complex string for:
        - Top 40% (1080x768): Cropped facecam scaled to 1080x768 using high-quality bicubic interpolation
        - Bottom 60% (1080x1152): Centered gameplay cropped and scaled to 1080x1152
        """
        fx, fy, fw, fh = face_box['x'], face_box['y'], face_box['w'], face_box['h']

        # Gameplay: 1080:1152 aspect ratio
        game_aspect = self.target_game_w / self.target_game_h # 1080 / 1152 = 0.9375
        game_crop_h = orig_h
        game_crop_w = int(orig_h * game_aspect)

        # Center horizontally in the remaining gameplay window
        game_crop_x = max(0, (orig_w - game_crop_w) // 2)
        game_crop_y = 0

        filter_str = (
            f"[0:v]split=2[v_face_in][v_game_in];"
            f"[v_face_in]crop={fw}:{fh}:{fx}:{fy},scale={self.target_face_w}:{self.target_face_h}:flags=bicubic[v_top];"
            f"[v_game_in]crop={game_crop_w}:{game_crop_h}:{game_crop_x}:{game_crop_y},scale={self.target_game_w}:{self.target_game_h}:flags=bicubic[v_bot];"
            f"[v_top][v_bot]vstack[v_out]"
        )

        return {
            "filter_complex": filter_str,
            "face_box": face_box,
            "game_crop": {"x": game_crop_x, "y": game_crop_y, "w": game_crop_w, "h": game_crop_h}
        }

    def _save_crop_previews(self, frame: np.ndarray, face_box: Dict[str, int], game_crop: Dict[str, int]):
        """Saves cropped preview snapshots for display in the dashboard framing column."""
        try:
            fx, fy, fw, fh = face_box['x'], face_box['y'], face_box['w'], face_box['h']
            face_crop = frame[fy:fy+fh, fx:fx+fw]
            if face_crop.size > 0:
                cv2.imwrite(str(settings.CLIPS_DIR / "preview_facecam.jpg"), face_crop)

            gx, gy, gw, gh = game_crop['x'], game_crop['y'], game_crop['w'], game_crop['h']
            game_crop_img = frame[gy:gy+gh, gx:gx+gw]
            if game_crop_img.size > 0:
                cv2.imwrite(str(settings.CLIPS_DIR / "preview_gameplay.jpg"), game_crop_img)

            state.col2_has_preview = True
            state.preview_version += 1
        except Exception as e:
            state.add_col2_log(f"Preview generation notice: {str(e)}")

facecam_cropper = FacecamCropper()
