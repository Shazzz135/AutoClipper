import cv2
import json
import numpy as np
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Any
from backend.core.config import settings
from backend.core.state import state

# Path to YuNet ONNX deep learning face detector model
YUNET_MODEL_PATH = settings.BASE_DIR / "backend" / "models" / "face_detection_yunet.onnx"
PROFILES_FILE = settings.BASE_DIR / "config" / "streamer_profiles.json"

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

    def load_streamer_boxes(self, channel: Optional[str] = None) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, int]]]:
        """Loads saved Red (face_box) and Blue (game_box) coordinates for the specified streamer from disk."""
        ch = (channel or settings.TWITCH_CHANNEL or "").strip().lower().lstrip("#")
        if not ch or not PROFILES_FILE.exists():
            return None, None
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            prof = data.get(ch, {})
            fb = prof.get("face_box")
            gb = prof.get("game_box")
            if fb and gb and fb.get("w", 0) > 0 and gb.get("w", 0) > 0:
                return fb, gb
        except Exception:
            pass
        return None, None

    def save_streamer_boxes(self, face_box: Dict[str, int], game_box: Dict[str, int], channel: Optional[str] = None):
        """Persists Red (face_box) and Blue (game_box) coordinates for the streamer to disk."""
        ch = (channel or settings.TWITCH_CHANNEL or "").strip().lower().lstrip("#")
        if not ch:
            return
        PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if PROFILES_FILE.exists():
            try:
                with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if ch not in data or not isinstance(data[ch], dict):
            data[ch] = {}
        data[ch]["face_box"] = face_box
        data[ch]["game_box"] = game_box
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Failed to save streamer boxes:", e)

    def analyze_and_compute_crops(self, video_path: Path, force_redetect: bool = False) -> Dict[str, Any]:
        """
        Performs a single 1-take guess of the streamer's facecam & gameplay layout on the first run,
        then locks it so user adjustments to the Red and Blue boxes are never overwritten or changed back.
        """
        orig_w, orig_h = 1280, 720
        temp_frame_path = settings.BUFFER_DIR / "temp_detect_frame.jpg"
        best_frame = None

        # Extract 1 representative frame from the video
        for seek_sec in [2, 1, 0]:
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(seek_sec),
                    "-i", str(video_path),
                    "-frames:v", "1",
                    "-update", "1",
                    str(temp_frame_path)
                ]
                subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if temp_frame_path.exists():
                    frame = cv2.imread(str(temp_frame_path))
                    if frame is not None:
                        best_frame = frame.copy()
                        orig_h, orig_w, _ = best_frame.shape
                        break
            except Exception:
                pass

        if temp_frame_path.exists():
            try:
                temp_frame_path.unlink()
            except Exception:
                pass

        # Check if streamer already has saved Red/Blue boxes on disk
        if not state.layout_locked and not force_redetect:
            saved_fb, saved_gb = self.load_streamer_boxes(settings.TWITCH_CHANNEL)
            if saved_fb and saved_gb:
                state.current_facecam_box = saved_fb
                state.current_gameplay_box = saved_gb
                state.layout_locked = True
                state.facecam_rule_applied = "SAVED STREAMER PROFILE"
                state.add_col2_log(f"Loaded saved Red/Blue boxes for #{settings.TWITCH_CHANNEL} from profile.")

        # If layout is already locked (from saved streamer profile, 1-take guess, or user Red/Blue box edit), NEVER change it or the preview frame back
        if state.layout_locked and state.current_facecam_box and state.current_gameplay_box and not force_redetect:
            crop_data = self.compute_custom_crop(state.current_facecam_box, state.current_gameplay_box, orig_w, orig_h)
            if not state.col2_has_preview and best_frame is not None:
                self._save_crop_previews(best_frame, crop_data["face_box"], crop_data["game_crop"])
            state.col2_status = "LOCKED"
            return crop_data

        # Otherwise: Perform ONE take to guess the initial layout, then lock it
        state.col2_status = "DETECTING"
        state.add_col2_log(f"Running 1-take initial layout guess on: {video_path.name}")

        face_result = self._detect_face_in_frame(best_frame) if best_frame is not None else None

        if face_result and best_frame is not None:
            left, top, fw, fh, conf = face_result
            box, rule_name = self._auto_expand_facecam_box(best_frame, left, top, fw, fh, orig_w, orig_h)
            state.current_facecam_box = box
            state.last_known_facecam = box
            state.using_fallback = False
            state.edge_confidence = float(conf)
            state.facecam_rule_applied = rule_name
            state.add_col2_log(f"1-Take layout guessed & locked: {rule_name} at ({box['x']}, {box['y']}) {box['w']}x{box['h']}")
        else:
            if state.last_known_facecam:
                box = state.last_known_facecam
            else:
                box = {
                    'x': int(orig_w * 0.05),
                    'y': int(orig_h * 0.55),
                    'w': int(orig_w * 0.32),
                    'h': int(orig_h * 0.40)
                }
            state.current_facecam_box = box
            state.last_known_facecam = box
            state.using_fallback = True
            state.edge_confidence = 0.75
            state.add_col2_log(f"1-Take fallback layout guessed & locked at ({box['x']}, {box['y']}). Adjust Red/Blue boxes if needed.")

        filter_data = self._generate_filter_complex(box, orig_w, orig_h)
        state.current_gameplay_box = filter_data["game_crop"]
        state.layout_locked = True
        state.col2_status = "LOCKED"
        self.save_streamer_boxes(box, filter_data["game_crop"], settings.TWITCH_CHANNEL)

        if best_frame is not None:
            self._save_crop_previews(best_frame, box, filter_data["game_crop"])

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

    def compute_adjusted_crop(
        self,
        base_face_box: Dict[str, int],
        zoom: float = 1.0,
        pan_x: int = 0,
        pan_y: int = 0,
        orig_w: int = 1280,
        orig_h: int = 720
    ) -> Dict[str, Any]:
        """
        Adjusts the facecam crop box based on user zoom (0.7x to 2.5x) and pan offsets.
        Re-computes FFmpeg filter complex for 40/60 vertical composition.
        """
        zoom = max(0.5, min(3.0, float(zoom)))
        bx = base_face_box.get('x', 0)
        by = base_face_box.get('y', 0)
        bw = base_face_box.get('w', 400)
        bh = base_face_box.get('h', 284)

        # Center point with pan offset
        cx = bx + bw // 2 + int(pan_x)
        cy = by + bh // 2 + int(pan_y)

        # Scale crop box by zoom (zoom > 1.0 means zoom in / tighter crop)
        target_aspect = self.target_face_w / self.target_face_h
        new_w = int(bw / zoom)
        new_h = int(new_w / target_aspect)

        # Clamp crop dimensions within canvas
        new_w = min(orig_w, max(120, new_w))
        new_h = min(orig_h, max(int(120 / target_aspect), new_h))

        # Clamp position within canvas
        new_x = max(0, min(orig_w - new_w, cx - new_w // 2))
        new_y = max(0, min(orig_h - new_h, cy - new_h // 2))

        # Even coordinates for FFmpeg
        w = new_w - (new_w % 2)
        h = new_h - (new_h % 2)
        x = new_x - (new_x % 2)
        y = new_y - (new_y % 2)

        adjusted_box = {'x': x, 'y': y, 'w': w, 'h': h}
        crop_data = self._generate_filter_complex(adjusted_box, orig_w, orig_h)
        crop_data["adjusted_box"] = adjusted_box
        crop_data["zoom"] = zoom
        crop_data["pan_x"] = pan_x
        crop_data["pan_y"] = pan_y
        return crop_data

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

    def compute_custom_crop(self, face_box: Dict[str, Any], game_box: Dict[str, Any], orig_w: int = 1280, orig_h: int = 720) -> Dict[str, Any]:
        """
        Computes 40/60 vertical composition from user-defined Red Box (Facecam) and Blue Box (Gameplay).
        """
        def _safe_int(val, default):
            try:
                return int(round(float(val)))
            except Exception:
                return default

        fx = max(0, min(orig_w - 20, _safe_int(face_box.get('x', 0), 0)))
        fy = max(0, min(orig_h - 20, _safe_int(face_box.get('y', 0), 0)))
        fw = max(20, min(orig_w - fx, _safe_int(face_box.get('w', 400), 400)))
        fh = max(20, min(orig_h - fy, _safe_int(face_box.get('h', 284), 284)))

        gx = max(0, min(orig_w - 20, _safe_int(game_box.get('x', 0), 0)))
        gy = max(0, min(orig_h - 20, _safe_int(game_box.get('y', 0), 0)))
        gw = max(20, min(orig_w - gx, _safe_int(game_box.get('w', 675), 675)))
        gh = max(20, min(orig_h - gy, _safe_int(game_box.get('h', 720), 720)))

        # Ensure even coordinates for FFmpeg
        fx -= (fx % 2)
        fy -= (fy % 2)
        fw = max(20, fw - (fw % 2))
        fh = max(20, fh - (fh % 2))

        gx -= (gx % 2)
        gy -= (gy % 2)
        gw = max(20, gw - (gw % 2))
        gh = max(20, gh - (gh % 2))

        cleaned_face = {'x': fx, 'y': fy, 'w': fw, 'h': fh}
        cleaned_game = {'x': gx, 'y': gy, 'w': gw, 'h': gh}

        # Enforce exact target aspect ratios inside the user's Red (1080:768) and Blue (1080:1152) boxes
        # so the 9:16 vertical Short NEVER stretches or distorts and NEVER adds black bars.
        face_aspect = self.target_face_w / self.target_face_h # 1.40625
        if (fw / fh) > face_aspect:
            eff_fh = fh
            eff_fw = int(round(fh * face_aspect))
        else:
            eff_fw = fw
            eff_fh = int(round(fw / face_aspect))
        eff_fw = max(20, min(orig_w, eff_fw - (eff_fw % 2)))
        eff_fh = max(20, min(orig_h, eff_fh - (eff_fh % 2)))
        eff_fx = max(0, min(orig_w - eff_fw, fx + (fw - eff_fw) // 2))
        eff_fy = max(0, min(orig_h - eff_fh, fy + (fh - eff_fh) // 2))
        eff_fx -= (eff_fx % 2)
        eff_fy -= (eff_fy % 2)

        game_aspect = self.target_game_w / self.target_game_h # 0.9375
        if (gw / gh) > game_aspect:
            eff_gh = gh
            eff_gw = int(round(gh * game_aspect))
        else:
            eff_gw = gw
            eff_gh = int(round(gw / game_aspect))
        eff_gw = max(20, min(orig_w, eff_gw - (eff_gw % 2)))
        eff_gh = max(20, min(orig_h, eff_gh - (eff_gh % 2)))
        eff_gx = max(0, min(orig_w - eff_gw, gx + (gw - eff_gw) // 2))
        eff_gy = max(0, min(orig_h - eff_gh, gy + (gh - eff_gh) // 2))
        eff_gx -= (eff_gx % 2)
        eff_gy -= (eff_gy % 2)

        filter_str = (
            f"[0:v]split=2[v_face_in][v_game_in];"
            f"[v_face_in]crop={eff_fw}:{eff_fh}:{eff_fx}:{eff_fy},scale={self.target_face_w}:{self.target_face_h}:flags=bicubic[v_top];"
            f"[v_game_in]crop={eff_gw}:{eff_gh}:{eff_gx}:{eff_gy},scale={self.target_game_w}:{self.target_game_h}:flags=bicubic[v_bot];"
            f"[v_top][v_bot]vstack[v_out]"
        )

        return {
            "filter_complex": filter_str,
            "face_box": cleaned_face,
            "game_crop": cleaned_game
        }

    def _get_or_extract_full_frame(self) -> np.ndarray:
        """
        Loads preview_full_frame.jpg, or extracts one from any available candidate/segment if missing.
        If no segment is ready yet, fetches a live stream frame via streamlink so Column 2 can be viewed and edited immediately.
        """
        full_frame_path = settings.CLIPS_DIR / "preview_full_frame.jpg"
        if full_frame_path.exists():
            frame = cv2.imread(str(full_frame_path))
            if frame is not None and frame.size > 0 and np.mean(frame) > 1.0:
                return frame

        # 1. Try extracting a frame from any candidate or stream buffer segment via OpenCV
        candidates = sorted(list(settings.CLIPS_DIR.glob("*_candidate.mp4")), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            candidates = sorted(list(settings.BUFFER_DIR.glob("*.ts")), key=lambda p: p.stat().st_mtime, reverse=True)
        for cand in candidates[:3]:
            try:
                cap = cv2.VideoCapture(str(cand))
                ok, frame = cap.read()
                cap.release()
                if ok and frame is not None and frame.size > 0:
                    cv2.imwrite(str(full_frame_path), frame)
                    return frame
            except Exception:
                pass

        # 2. Try extracting via ffmpeg from the latest .ts segment
        for cand in candidates[:2]:
            try:
                cmd = ["ffmpeg", "-y", "-i", str(cand), "-frames:v", "1", "-update", "1", str(full_frame_path)]
                subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if full_frame_path.exists():
                    frame = cv2.imread(str(full_frame_path))
                    if frame is not None and frame.size > 0:
                        return frame
            except Exception:
                pass

        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def refresh_live_stream_frame(self) -> Optional[Dict[str, Any]]:
        """
        Captures a single stream frame once for Column 2 and locks it so that one frame lasts the entire time.
        """
        if state.col2_has_preview and state.layout_locked and state.current_facecam_box and state.current_gameplay_box:
            return self.compute_custom_crop(
                state.current_facecam_box,
                state.current_gameplay_box,
                state.frame_dimensions.get("w", 1280),
                state.frame_dimensions.get("h", 720)
            )

        segments = sorted(list(settings.BUFFER_DIR.glob("seg_*.ts")), key=lambda p: p.stat().st_mtime, reverse=True)
        if not segments:
            return None

        latest_seg = next((s for s in segments if s.stat().st_size > 30000), None)
        if not latest_seg:
            return None

        return self.analyze_and_compute_crops(latest_seg)

    def update_boxes_from_full_frame(self, face_box: Dict[str, Any], game_box: Dict[str, Any]) -> Dict[str, Any]:
        """
        Loads saved full frame, computes custom crop from user boxes, locks layout, saves to streamer profile, and updates preview images & state.
        """
        frame = self._get_or_extract_full_frame()
        orig_h, orig_w = frame.shape[:2]
        crop_data = self.compute_custom_crop(face_box, game_box, orig_w, orig_h)
        state.layout_locked = True
        state.col2_status = "LOCKED"
        self.save_streamer_boxes(crop_data["face_box"], crop_data["game_crop"], settings.TWITCH_CHANNEL)
        self._save_crop_previews(frame, crop_data["face_box"], crop_data["game_crop"])
        return crop_data

    def reset_to_ai_guess(self) -> Dict[str, Any]:
        """
        Explicitly re-runs 1-take AI detection on the full frame when user clicks 'RESET TO AI BOXES'.
        """
        frame = self._get_or_extract_full_frame()
        orig_h, orig_w = frame.shape[:2]
        face_result = self._detect_face_in_frame(frame)
        if face_result:
            left, top, fw, fh, conf = face_result
            box, rule_name = self._auto_expand_facecam_box(frame, left, top, fw, fh, orig_w, orig_h)
            state.edge_confidence = float(conf)
            state.using_fallback = False
            state.facecam_rule_applied = rule_name
        else:
            box = {
                'x': int(orig_w * 0.05),
                'y': int(orig_h * 0.55),
                'w': int(orig_w * 0.32),
                'h': int(orig_h * 0.40)
            }
            state.using_fallback = True

        filter_data = self._generate_filter_complex(box, orig_w, orig_h)
        state.layout_locked = True
        state.col2_status = "LOCKED"
        self.save_streamer_boxes(filter_data["face_box"], filter_data["game_crop"], settings.TWITCH_CHANNEL)
        self._save_crop_previews(frame, filter_data["face_box"], filter_data["game_crop"])
        return filter_data

    def _save_crop_previews(self, frame: np.ndarray, face_box: Dict[str, int], game_crop: Dict[str, int]):
        """Saves cropped preview snapshots for display in the dashboard framing column."""
        try:
            # Save full stream frame for interactive live editor
            full_frame_path = settings.CLIPS_DIR / "preview_full_frame.jpg"
            cv2.imwrite(str(full_frame_path), frame)

            fx, fy, fw, fh = face_box['x'], face_box['y'], face_box['w'], face_box['h']
            face_crop = frame[fy:fy+fh, fx:fx+fw]
            if face_crop.size > 0:
                cv2.imwrite(str(settings.CLIPS_DIR / "preview_facecam.jpg"), face_crop)

            gx, gy, gw, gh = game_crop['x'], game_crop['y'], game_crop['w'], game_crop['h']
            game_crop_img = frame[gy:gy+gh, gx:gx+gw]
            if game_crop_img.size > 0:
                cv2.imwrite(str(settings.CLIPS_DIR / "preview_gameplay.jpg"), game_crop_img)

            state.current_facecam_box = face_box
            state.current_gameplay_box = game_crop
            state.frame_dimensions = {"w": frame.shape[1], "h": frame.shape[0]}
            state.col2_has_preview = True
            state.preview_version += 1
        except Exception as e:
            state.add_col2_log(f"Preview generation notice: {str(e)}")

facecam_cropper = FacecamCropper()
