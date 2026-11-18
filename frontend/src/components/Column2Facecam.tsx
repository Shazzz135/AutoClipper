import React, { useState, useRef, useEffect } from 'react';
import {
  ScanFace,
  LayoutTemplate,
  Terminal,
  Image as ImageIcon,
  Sliders,
  CheckCircle2,
  X,
  Move,
  Maximize2,
  RotateCcw,
  Save,
  AlertCircle
} from 'lucide-react';

export default function Column2Facecam({ data }) {
  const status = data?.status || 'IDLE';
  const box = data?.current_facecam_box || { x: 0, y: 0, w: 0, h: 0 };
  const edgeConf = (data?.edge_confidence || 0) * 100;
  const usingFallback = data?.using_fallback || false;
  const logs = data?.logs || [];
  const hasPreview = data?.has_preview || false;
  const previewVersion = data?.preview_version || 1;
  const facecamUrl = data?.facecam_preview_url;
  const gameplayUrl = data?.gameplay_preview_url;
  const fullFrameUrl = data?.full_frame_preview_url;
  const currentMode = data?.facecam_mode || 'AUTO';
  const ruleApplied = data?.rule_applied || 'RULE 1: FIT BOX (1080x768)';
  const hasBackground = data?.has_background !== false;

  const [togglingMode, setTogglingMode] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorNotice, setEditorNotice] = useState(null);
  const [isSavingBoxes, setIsSavingBoxes] = useState(false);

  // Live Red/Blue Box state for editor
  const frameDim = data?.frame_dimensions || { w: 1280, h: 720 };
  const [faceBox, setFaceBox] = useState({ x: 0, y: 0, w: 400, h: 284 });
  const [gameBox, setGameBox] = useState({ x: 300, y: 0, w: 675, h: 720 });
  const [activeBox, setActiveBox] = useState('face'); // 'face' or 'game'

  // Refs to prevent state stomping from incoming WebSocket packets
  const faceBoxRef = useRef(faceBox);
  const gameBoxRef = useRef(gameBox);
  faceBoxRef.current = faceBox;
  gameBoxRef.current = gameBox;
  const userEditedRef = useRef(false);

  // Dragging and resizing state
  const editorCanvasRef = useRef(null);
  const dragRef = useRef(null);

  useEffect(() => {
    // DO NOT overwrite if user has modified boxes or if modal is open
    if (isEditorOpen || userEditedRef.current || dragRef.current) return;

    if (data?.current_facecam_box && data.current_facecam_box.w > 0) {
      setFaceBox(data.current_facecam_box);
    }
    if (data?.current_gameplay_box && data.current_gameplay_box.w > 0) {
      setGameBox(data.current_gameplay_box);
    } else {
      // Default gameplay crop: 1080:1152 aspect centered
      const gh = frameDim.h;
      const gw = Math.round(gh * (1080 / 1152));
      const gx = Math.max(0, Math.round((frameDim.w - gw) / 2));
      setGameBox({ x: gx, y: 0, w: gw, h: gh });
    }
  }, [data?.current_facecam_box, data?.current_gameplay_box, isEditorOpen]);

  const handleOpenEditor = async () => {
    if (!hasPreview || !fullFrameUrl) {
      setEditorNotice('Running 1-take layout detection...');
      try {
        const res = await fetch('/api/facecam/init_preview', { method: 'POST' });
        if (res.ok) {
          const resData = await res.json();
          if (resData?.crop_data?.face_box) {
            faceBoxRef.current = resData.crop_data.face_box;
            setFaceBox(resData.crop_data.face_box);
          }
          if (resData?.crop_data?.game_crop) {
            gameBoxRef.current = resData.crop_data.game_crop;
            setGameBox(resData.crop_data.game_crop);
          }
          setEditorNotice(null);
          setIsEditorOpen(true);
          return;
        }
      } catch (e) {
        console.error(e);
      }
      setEditorNotice('Waiting for stream buffer frame before editing crop boxes.');
      setTimeout(() => setEditorNotice(null), 4000);
      return;
    }
    // Only load from data if user hasn't edited yet
    if (!userEditedRef.current) {
      if (data?.current_facecam_box && data.current_facecam_box.w > 0) {
        setFaceBox(data.current_facecam_box);
      }
      if (data?.current_gameplay_box && data.current_gameplay_box.w > 0) {
        setGameBox(data.current_gameplay_box);
      }
    }
    setIsEditorOpen(true);
  };

  const handleMouseDown = (e, boxType, actionType) => {
    e.stopPropagation();
    e.preventDefault();
    setActiveBox(boxType);
    userEditedRef.current = true;

    if (!editorCanvasRef.current) return;
    const rect = editorCanvasRef.current.getBoundingClientRect();
    const currentTargetBox = boxType === 'face' ? faceBoxRef.current : gameBoxRef.current;

    dragRef.current = {
      boxType,
      actionType, // 'move', 'nw', 'ne', 'sw', 'se'
      startX: e.clientX,
      startY: e.clientY,
      rectWidth: rect.width,
      rectHeight: rect.height,
      initBox: { ...currentTargetBox }
    };

    const handleMouseMove = (moveEvent) => {
      if (!dragRef.current) return;
      const { boxType, actionType, startX, startY, rectWidth, rectHeight, initBox } = dragRef.current;
      const deltaX = Math.round(((moveEvent.clientX - startX) / rectWidth) * frameDim.w);
      const deltaY = Math.round(((moveEvent.clientY - startY) / rectHeight) * frameDim.h);

      let nextBox = { ...initBox };

      if (actionType === 'move') {
        nextBox.x = Math.max(0, Math.min(frameDim.w - initBox.w, initBox.x + deltaX));
        nextBox.y = Math.max(0, Math.min(frameDim.h - initBox.h, initBox.y + deltaY));
      } else if (actionType === 'se') {
        nextBox.w = Math.max(40, Math.min(frameDim.w - initBox.x, initBox.w + deltaX));
        nextBox.h = Math.max(40, Math.min(frameDim.h - initBox.y, initBox.h + deltaY));
      } else if (actionType === 'nw') {
        const nx = Math.max(0, Math.min(initBox.x + initBox.w - 40, initBox.x + deltaX));
        const ny = Math.max(0, Math.min(initBox.y + initBox.h - 40, initBox.y + deltaY));
        nextBox.w = initBox.w + (initBox.x - nx);
        nextBox.h = initBox.h + (initBox.y - ny);
        nextBox.x = nx;
        nextBox.y = ny;
      } else if (actionType === 'ne') {
        const ny = Math.max(0, Math.min(initBox.y + initBox.h - 40, initBox.y + deltaY));
        nextBox.w = Math.max(40, Math.min(frameDim.w - initBox.x, initBox.w + deltaX));
        nextBox.h = initBox.h + (initBox.y - ny);
        nextBox.y = ny;
      } else if (actionType === 'sw') {
        const nx = Math.max(0, Math.min(initBox.x + initBox.w - 40, initBox.x + deltaX));
        nextBox.w = initBox.w + (initBox.x - nx);
        nextBox.h = Math.max(40, Math.min(frameDim.h - initBox.y, initBox.h + deltaY));
        nextBox.x = nx;
      }

      if (boxType === 'face') {
        faceBoxRef.current = nextBox;
        setFaceBox(nextBox);
      } else {
        gameBoxRef.current = nextBox;
        setGameBox(nextBox);
      }
    };

    const handleMouseUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleSaveCropBoxes = async () => {
    setIsSavingBoxes(true);
    try {
      const res = await fetch('/api/facecam/update_boxes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ face_box: faceBoxRef.current, game_box: gameBoxRef.current })
      });
      if (res.ok) {
        const resData = await res.json();
        if (resData?.crop_data?.face_box) {
          faceBoxRef.current = resData.crop_data.face_box;
          setFaceBox(resData.crop_data.face_box);
        }
        if (resData?.crop_data?.game_crop) {
          gameBoxRef.current = resData.crop_data.game_crop;
          setGameBox(resData.crop_data.game_crop);
        }
        // Keep userEditedRef = true so in-flight WebSocket ticks never revert user boxes
        userEditedRef.current = true;
        setIsEditorOpen(false);
      } else {
        const err = await res.json();
        alert(`Failed to save crop boxes: ${err.detail || 'Error'}`);
      }
    } catch (e) {
      console.error(e);
      alert('Error saving custom crop boxes');
    } finally {
      setIsSavingBoxes(false);
    }
  };

  const handleResetToAi = async () => {
    setIsSavingBoxes(true);
    try {
      const res = await fetch('/api/facecam/reset_ai', { method: 'POST' });
      if (res.ok) {
        const resData = await res.json();
        if (resData?.crop_data?.face_box) {
          faceBoxRef.current = resData.crop_data.face_box;
          setFaceBox(resData.crop_data.face_box);
        }
        if (resData?.crop_data?.game_crop) {
          gameBoxRef.current = resData.crop_data.game_crop;
          setGameBox(resData.crop_data.game_crop);
        }
        userEditedRef.current = false;
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSavingBoxes(false);
    }
  };

  const handleModeChange = async (mode) => {
    setTogglingMode(true);
    try {
      await fetch('/api/facecam/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
    } catch (e) {
      console.error('Failed to change facecam mode', e);
    } finally {
      setTogglingMode(false);
    }
  };

  const getStatusBg = (s) => {
    if (s === 'IDLE') return 'bg-[#262b34] text-[#88909e]';
    if (s.includes('DETECT') || s.includes('CROP')) return 'bg-yellow-500 text-black animate-pulse';
    if (s === 'OK' || s === 'READY' || s.includes('LOCK')) return 'bg-[#00e676] text-black font-bold';
    return 'bg-[#262b34] text-white';
  };

  return (
    <div className="flex flex-col h-full bg-[#0d0f12] border-r border-[#262b34] font-mono select-none">
      {/* Column Header */}
      <div className="p-3 border-b border-[#262b34] flex items-center justify-between bg-[#14171d]">
        <div className="flex items-center space-x-2">
          <ScanFace className="w-4 h-4 text-blue-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-white">
            COLUMN 2: FACECAM & FRAMING
          </h2>
        </div>
        <span className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded ${getStatusBg(status)}`}>
          {status}
        </span>
      </div>

      <div className="flex-1 p-3 space-y-3 overflow-y-auto">
        {/* Facecam Detection HUD */}
        <div className="border border-[#262b34] bg-[#14171d] p-3 space-y-2.5">
          <div className="text-[10px] font-bold text-[#88909e] uppercase flex items-center justify-between">
            <span>YUNET NEURAL DETECTION</span>
            <span className="text-[9px] text-blue-400">INPUT: 1280 x 720</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
            <div className="bg-[#0d0f12] p-2 border border-[#262b34]">
              <div className="text-[#88909e] text-[9px] uppercase">Face Bounding Box</div>
              <div className="text-white font-bold mt-0.5">
                X:{box.x} Y:{box.y}
              </div>
              <div className="text-[#88909e] text-[10px]">
                {box.w} x {box.h} px
              </div>
            </div>

            <div className="bg-[#0d0f12] p-2 border border-[#262b34]">
              <div className="text-[#88909e] text-[9px] uppercase">Edge Confidence</div>
              <div className="text-[#00e676] font-bold mt-0.5">
                {edgeConf.toFixed(1)}%
              </div>
              <div className="text-[#88909e] text-[10px]">
                {usingFallback ? 'USING FALLBACK' : 'AI CONFIRMED'}
              </div>
            </div>
          </div>
        </div>

        {/* 40/60 Split Layout Preview & Interactive Click to Edit */}
        <div className="border border-[#262b34] bg-[#14171d] p-3 space-y-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase flex items-center justify-between">
            <span className="flex items-center gap-1 text-white">
              <LayoutTemplate className="w-3.5 h-3.5 text-blue-400" />
              40/60 CANVAS COMPOSITION (1080x1920)
            </span>
            <button
              type="button"
              onClick={handleOpenEditor}
              className="text-[9px] font-bold text-white bg-blue-600 hover:bg-blue-500 px-2 py-0.5 border border-blue-400 flex items-center gap-1 transition-none cursor-pointer"
            >
              <Maximize2 className="w-2.5 h-2.5" />
              EDIT RED/BLUE BOXES
            </button>
          </div>

          {editorNotice && (
            <div className="text-[10px] text-yellow-400 bg-yellow-400/10 p-2 border border-yellow-400/30 flex items-center gap-1.5">
              <AlertCircle className="w-3 h-3 shrink-0" />
              <span>{editorNotice}</span>
            </div>
          )}

          <div className="flex gap-3 items-center">
            {/* Visual 9:16 Preview Box - Clickable to open Live Editor */}
            <div
              onClick={handleOpenEditor}
              title="Click to open Live Red/Blue Crop Box Editor"
              className="w-28 h-48 border-2 border-blue-500 cursor-pointer hover:border-[#00e676] bg-black flex flex-col shrink-0 overflow-hidden relative shadow-lg group"
            >
              {/* Top 40% Facecam Slot */}
              <div className="h-[40%] border-b border-red-500/60 bg-[#0d0f12] overflow-hidden relative flex items-center justify-center">
                {hasPreview && facecamUrl ? (
                  <img
                    src={`${facecamUrl}?v=${previewVersion}`}
                    alt="Facecam Crop"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center p-1">
                    <div className="text-[8px] text-red-400 font-bold uppercase">40% Facecam</div>
                    <div className="text-[7px] text-[#88909e]">1080x768</div>
                  </div>
                )}
                <span className="absolute top-0.5 left-0.5 bg-black/80 px-1 text-[7px] text-red-400 font-bold uppercase">
                  RED BOX
                </span>
              </div>

              {/* Bottom 60% Gameplay Slot */}
              <div className="h-[60%] bg-[#0d0f12] overflow-hidden relative flex items-center justify-center">
                {hasPreview && gameplayUrl ? (
                  <img
                    src={`${gameplayUrl}?v=${previewVersion}`}
                    alt="Gameplay Crop"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center p-1">
                    <div className="text-[8px] text-blue-400 font-bold uppercase">60% Gameplay</div>
                    <div className="text-[7px] text-[#88909e]">1080x1152</div>
                  </div>
                )}
                <span className="absolute top-0.5 left-0.5 bg-black/80 px-1 text-[7px] text-blue-400 font-bold uppercase">
                  BLUE BOX
                </span>
              </div>

              {/* Hover overlay hint */}
              {hasPreview && (
                <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center text-center p-1 transition-opacity">
                  <Maximize2 className="w-4 h-4 text-[#00e676] mb-0.5" />
                  <span className="text-[8px] text-white font-bold uppercase leading-tight">
                    CLICK TO EDIT BOXES
                  </span>
                </div>
              )}
            </div>

            {/* Geometry Details */}
            <div className="text-[10px] space-y-1 text-[#88909e]">
              <div><strong className="text-white">Canvas:</strong> 9:16 (1080x1920)</div>
              <div><strong className="text-red-400">Red Box (Top 40%):</strong> Facecam (1080x768)</div>
              <div><strong className="text-blue-400">Blue Box (Bot 60%):</strong> Gameplay (1080x1152)</div>
              <div><strong className="text-white">Live Editor:</strong> {hasPreview ? 'Ready (Click Preview)' : 'Awaiting Face Recon'}</div>
              {hasPreview && (
                <button
                  type="button"
                  onClick={handleOpenEditor}
                  className="mt-1 text-[9px] text-[#00e676] hover:underline flex items-center gap-1 font-bold"
                >
                  &rarr; Open Visual Crop Box Editor
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Framing Logs */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center gap-1">
            <Terminal className="w-3 h-3" />
            FRAMING LOGS
          </div>
          <div className="h-32 overflow-y-auto text-[10px] space-y-0.5 bg-[#0d0f12] p-1.5 border border-[#262b34] text-[#88909e]">
            {logs.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap">{l}</div>
            ))}
          </div>
        </div>
      </div>

      {/* LIVE RED/BLUE CROP BOX EDITOR MODAL */}
      {isEditorOpen && (
        <div className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4">
          <div className="bg-[#14171d] border-2 border-blue-500 w-full max-w-4xl p-4 space-y-3 shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-[#262b34] pb-2">
              <div>
                <h3 className="text-sm font-bold text-white uppercase flex items-center gap-2">
                  <Maximize2 className="w-4 h-4 text-blue-400" />
                  <span>LIVE CROP BOX EDITOR (1280 x 720 STREAM CANVAS)</span>
                </h3>
                <p className="text-[10px] text-[#88909e] mt-0.5">
                  Drag boxes to move. Drag corners to expand/resize.
                  <span className="text-red-400 font-bold ml-1">■ Red = Facecam (Top 40%)</span>
                  <span className="text-blue-400 font-bold ml-2">■ Blue = Gameplay (Bottom 60%)</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsEditorOpen(false)}
                className="text-[#88909e] hover:text-white p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Visual Stream Canvas with Draggable/Resizable Boxes */}
            <div
              ref={editorCanvasRef}
              className="relative w-full aspect-video bg-black border border-[#262b34] overflow-hidden select-none"
            >
              {fullFrameUrl && (
                <img
                  src={`${fullFrameUrl}?v=${previewVersion}`}
                  alt="Full Stream Frame"
                  className="w-full h-full object-contain pointer-events-none"
                />
              )}

              {/* BLUE BOX: Gameplay (Bottom 60%) */}
              <div
                onMouseDown={(e) => handleMouseDown(e, 'game', 'move')}
                style={{
                  left: `${(gameBox.x / frameDim.w) * 100}%`,
                  top: `${(gameBox.y / frameDim.h) * 100}%`,
                  width: `${(gameBox.w / frameDim.w) * 100}%`,
                  height: `${(gameBox.h / frameDim.h) * 100}%`
                }}
                className={`absolute border-2 ${activeBox === 'game' ? 'border-blue-400 bg-blue-500/25 ring-2 ring-blue-400/50' : 'border-blue-600/70 bg-blue-600/15'} cursor-move transition-shadow`}
              >
                <div className="absolute top-0 left-0 bg-blue-600 text-white text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider flex items-center gap-1 pointer-events-none">
                  <Move className="w-2.5 h-2.5" />
                  BLUE: GAMEPLAY (BOT 60%) [{gameBox.w}x{gameBox.h}]
                </div>

                {/* Resize handles */}
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'game', 'nw')}
                  className="absolute -top-1.5 -left-1.5 w-3 h-3 bg-blue-400 border border-white cursor-nw-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'game', 'ne')}
                  className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-blue-400 border border-white cursor-ne-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'game', 'sw')}
                  className="absolute -bottom-1.5 -left-1.5 w-3 h-3 bg-blue-400 border border-white cursor-sw-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'game', 'se')}
                  className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-blue-400 border border-white cursor-se-resize"
                />
              </div>

              {/* RED BOX: Facecam (Top 40%) */}
              <div
                onMouseDown={(e) => handleMouseDown(e, 'face', 'move')}
                style={{
                  left: `${(faceBox.x / frameDim.w) * 100}%`,
                  top: `${(faceBox.y / frameDim.h) * 100}%`,
                  width: `${(faceBox.w / frameDim.w) * 100}%`,
                  height: `${(faceBox.h / frameDim.h) * 100}%`
                }}
                className={`absolute border-2 ${activeBox === 'face' ? 'border-red-500 bg-red-500/30 ring-2 ring-red-400/50' : 'border-red-600/80 bg-red-600/20'} cursor-move z-10 transition-shadow`}
              >
                <div className="absolute top-0 left-0 bg-[#ff1e1e] text-white text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider flex items-center gap-1 pointer-events-none">
                  <Move className="w-2.5 h-2.5" />
                  RED: FACECAM (TOP 40%) [{faceBox.w}x{faceBox.h}]
                </div>

                {/* Resize handles */}
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'face', 'nw')}
                  className="absolute -top-1.5 -left-1.5 w-3 h-3 bg-red-500 border border-white cursor-nw-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'face', 'ne')}
                  className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-red-500 border border-white cursor-ne-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'face', 'sw')}
                  className="absolute -bottom-1.5 -left-1.5 w-3 h-3 bg-red-500 border border-white cursor-sw-resize"
                />
                <div
                  onMouseDown={(e) => handleMouseDown(e, 'face', 'se')}
                  className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-red-500 border border-white cursor-se-resize"
                />
              </div>
            </div>

            {/* Coordinates & Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-[#262b34]">
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-red-400 font-bold bg-[#0d0f12] px-2 py-1 border border-red-500/30">
                  RED FACE: X:{faceBox.x} Y:{faceBox.y} ({faceBox.w}x{faceBox.h})
                </span>
                <span className="text-blue-400 font-bold bg-[#0d0f12] px-2 py-1 border border-blue-500/30">
                  BLUE GAME: X:{gameBox.x} Y:{gameBox.y} ({gameBox.w}x{gameBox.h})
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleResetToAi}
                  className="bg-[#1a1f27] hover:bg-[#262b34] text-[#88909e] hover:text-white px-3 py-1.5 text-xs font-bold border border-[#262b34] flex items-center gap-1"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  RESET TO AI BOXES
                </button>
                <button
                  type="button"
                  onClick={handleSaveCropBoxes}
                  disabled={isSavingBoxes}
                  className="bg-[#00e676] hover:bg-[#00c853] text-black px-4 py-1.5 text-xs font-bold flex items-center gap-1.5 transition-none cursor-pointer"
                >
                  <Save className="w-3.5 h-3.5" />
                  {isSavingBoxes ? 'SAVING BOXES...' : 'APPLY & SAVE CROP BOXES'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
