import React, { useState, useRef, useEffect } from 'react';
import {
  Film,
  Scissors,
  Play,
  Pause,
  Volume2,
  VolumeX,
  Move,
  RotateCcw,
  Save,
  Trash2,
  Sparkles,
  CheckCircle2,
  Terminal,
  Edit3
} from 'lucide-react';

export default function ClipStudio({ state, activeClip, activeClipId, onClipCreated, onDiscardClip }) {
  const col2 = state?.col2 || {};
  const col3 = state?.col3 || {};
  const channel = state?.channel || 'streamer';
  const [mediaSize, setMediaSize] = useState({ w: 1280, h: 720 });
  const actualW = mediaSize.w || frameDim.w || 1280;
  const actualH = mediaSize.h || frameDim.h || 720;
  const frameDim = { w: actualW, h: actualH };
  const fullFrameUrl = col2?.full_frame_preview_url;
  const previewVersion = col2?.preview_version || 1;

  // Red (Facecam) and Blue (Gameplay) Box State
  const [faceBox, setFaceBox] = useState({ x: 64, y: 396, w: 400, h: 284 });
  const [gameBox, setGameBox] = useState({ x: 302, y: 0, w: 675, h: 720 });
  const [activeBox, setActiveBox] = useState('face');
  const [isSavingBoxes, setIsSavingBoxes] = useState(false);
  const [boxSaveNotice, setBoxSaveNotice] = useState(null);

  const faceBoxRef = useRef(faceBox);
  const gameBoxRef = useRef(gameBox);
  faceBoxRef.current = faceBox;
  gameBoxRef.current = gameBox;
  const userEditedBoxesRef = useRef(false);
  const lastChannelRef = useRef(channel);

  // Reset local box lock only when switching to a different streamer
  useEffect(() => {
    if (lastChannelRef.current !== channel) {
      lastChannelRef.current = channel;
      userEditedBoxesRef.current = false;
    }
  }, [channel]);

  useEffect(() => {
    if (userEditedBoxesRef.current || dragRef.current) return;
    if (col2?.current_facecam_box && col2.current_facecam_box.w > 0) {
      setFaceBox(col2.current_facecam_box);
      faceBoxRef.current = col2.current_facecam_box;
    }
    if (col2?.current_gameplay_box && col2.current_gameplay_box.w > 0) {
      setGameBox(col2.current_gameplay_box);
      gameBoxRef.current = col2.current_gameplay_box;
    }
  }, [col2?.current_facecam_box, col2?.current_gameplay_box, channel]);

  // 16:9 4-Minute (240s: 3m before + 1m after peak) Video Player & Range State
  const [videoDuration, setVideoDuration] = useState(240.0);
  const candidateDuration = videoDuration > 10 ? videoDuration : 240.0;
  const peakOffset = Number(activeClip?.peak_offset_sec ?? 180.0);
  const [trimStart, setTrimStart] = useState(155.0);
  const [trimEnd, setTrimEnd] = useState(200.0);
  const [currentVideoTime, setCurrentVideoTime] = useState(0.0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [customTitle, setCustomTitle] = useState('');
  const [isGeneratingTitle, setIsGeneratingTitle] = useState(false);
  const [isCreatingClip, setIsCreatingClip] = useState(false);
  const [createStatus, setCreateStatus] = useState(null);

  const handleRegenerateTitle = async () => {
    if (!activeClipId) return;
    setIsGeneratingTitle(true);
    try {
      const res = await fetch(`/api/clips/${activeClipId}/generate_ai`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data?.metadata?.title) {
          setCustomTitle(data.metadata.title);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsGeneratingTitle(false);
    }
  };

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const timelineRef = useRef(null);
  const timelineDragRef = useRef(null);
  const wasDraggingTimelineRef = useRef(false);
  const loadedClipIdRef = useRef(null);

  useEffect(() => {
    if (activeClip && activeClip.clip_id !== loadedClipIdRef.current) {
      loadedClipIdRef.current = activeClip.clip_id;
      setTrimStart(Number(activeClip.trim_start ?? 155.0));
      setTrimEnd(Number(activeClip.trim_end ?? 200.0));
      setCustomTitle(activeClip.title || '');
      setCurrentVideoTime(0.0);
      setIsPlaying(false);
      setCreateStatus(null);
    } else if (activeClip && activeClip.title && !customTitle) {
      setCustomTitle(activeClip.title);
    } else if (!activeClip) {
      loadedClipIdRef.current = null;
      setIsPlaying(false);
      setCurrentVideoTime(0.0);
    }
  }, [activeClip]);

  const selectedDuration = Math.max(0, trimEnd - trimStart);
  const hasActiveCandidateVideo = Boolean(activeClip && activeClip.candidate_video_file);
  const candidateVideoUrl = hasActiveCandidateVideo ? `/media/${activeClip.candidate_video_file}` : null;

  // Persist Red & Blue boxes for this streamer on backend
  const persistStreamerBoxes = async (fb, gb, showNotice = false) => {
    setIsSavingBoxes(true);
    try {
      const res = await fetch('/api/facecam/update_boxes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ face_box: fb, game_box: gb })
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
        if (showNotice) {
          setBoxSaveNotice(`✓ Saved Red/Blue boxes for #${channel}`);
          setTimeout(() => setBoxSaveNotice(null), 2500);
        }
      }
    } catch (e) {
      console.error('Error saving boxes:', e);
    } finally {
      setIsSavingBoxes(false);
    }
  };

  // Dragging & Resizing Red and Blue Boxes (Always Draggable on 16:9 Canvas)
  const handleBoxMouseDown = (e, boxType, actionType) => {
    e.stopPropagation();
    e.preventDefault();
    setActiveBox(boxType);
    userEditedBoxesRef.current = true;

    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
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
      // Automatically persist updated Red & Blue boxes for this streamer
      persistStreamerBoxes(faceBoxRef.current, gameBoxRef.current, true);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleClearAll = async () => {
    setIsSavingBoxes(true);
    try {
      if (hasActiveCandidateVideo && onDiscardClip) {
        handleDiscard();
      }
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
        userEditedBoxesRef.current = false;
        setCustomTitle('');
        setBoxSaveNotice(`✓ Cleared & reset for #${channel}`);
        setTimeout(() => setBoxSaveNotice(null), 2500);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSavingBoxes(false);
    }
  };

  // Video Controls
  const togglePlayPause = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play();
      setIsPlaying(true);
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const toggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !videoRef.current.muted;
    setIsMuted(videoRef.current.muted);
  };

  const handlePlayRange = () => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = trimStart;
    videoRef.current.play();
    setIsPlaying(true);
  };

  // Interactive 2-Minute Timeline (Seek Playhead + Drag Start/End/Window)
  const seekVideoTo = (timeSec) => {
    const clamped = Math.max(0, Math.min(candidateDuration, Math.round(timeSec * 10) / 10));
    setCurrentVideoTime(clamped);
    if (videoRef.current) {
      videoRef.current.currentTime = clamped;
    }
  };

  const stepPlayhead = (deltaSec) => {
    seekVideoTo(currentVideoTime + deltaSec);
  };

  const adjustTrimStart = (val) => {
    let newStart = Math.max(0, Math.min(trimEnd - 3.0, Number(val) || 0));
    if (trimEnd - newStart > 60.0) {
      newStart = trimEnd - 60.0;
    }
    const rounded = Math.round(newStart * 10) / 10;
    setTrimStart(rounded);
    seekVideoTo(rounded);
  };

  const adjustTrimEnd = (val) => {
    let newEnd = Math.min(candidateDuration, Math.max(trimStart + 3.0, Number(val) || 0));
    if (newEnd - trimStart > 60.0) {
      newEnd = trimStart + 60.0;
    }
    const rounded = Math.round(newEnd * 10) / 10;
    setTrimEnd(rounded);
    seekVideoTo(rounded);
  };

  const handleTimelineMouseDown = (e, actionType) => {
    e.stopPropagation();
    e.preventDefault();
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();

    if (actionType === 'playhead') {
      const clickRatio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      seekVideoTo(clickRatio * candidateDuration);
    }

    timelineDragRef.current = {
      actionType, // 'start', 'end', 'move', 'playhead'
      startX: e.clientX,
      rectLeft: rect.left,
      rectWidth: rect.width,
      initStart: trimStart,
      initEnd: trimEnd
    };

    const handleMouseMove = (moveEvent) => {
      if (!timelineDragRef.current) return;
      const { actionType, startX, rectLeft, rectWidth, initStart, initEnd } = timelineDragRef.current;
      const deltaRatio = (moveEvent.clientX - startX) / rectWidth;
      const deltaTime = deltaRatio * candidateDuration;

      if (actionType === 'playhead') {
        const posRatio = Math.max(0, Math.min(1, (moveEvent.clientX - rectLeft) / rectWidth));
        seekVideoTo(posRatio * candidateDuration);
      } else if (actionType === 'start') {
        let newStart = Math.max(0, Math.min(initEnd - 3.0, initStart + deltaTime));
        if (initEnd - newStart > 60.0) {
          newStart = initEnd - 60.0;
        }
        const rounded = Math.round(newStart * 10) / 10;
        setTrimStart(rounded);
        seekVideoTo(rounded);
      } else if (actionType === 'end') {
        let newEnd = Math.min(candidateDuration, Math.max(initStart + 3.0, initEnd + deltaTime));
        if (newEnd - initStart > 60.0) {
          newEnd = initStart + 60.0;
        }
        const rounded = Math.round(newEnd * 10) / 10;
        setTrimEnd(rounded);
        seekVideoTo(rounded);
      } else if (actionType === 'move') {
        const span = initEnd - initStart;
        let newStart = initStart + deltaTime;
        let newEnd = initEnd + deltaTime;
        if (newStart < 0) {
          newStart = 0;
          newEnd = span;
        } else if (newEnd > candidateDuration) {
          newEnd = candidateDuration;
          newStart = candidateDuration - span;
        }
        const rStart = Math.round(newStart * 10) / 10;
        const rEnd = Math.round(newEnd * 10) / 10;
        setTrimStart(rStart);
        setTrimEnd(rEnd);
        seekVideoTo(rStart);
      }
    };

    const handleMouseUp = () => {
      timelineDragRef.current = null;
      wasDraggingTimelineRef.current = true;
      setTimeout(() => { wasDraggingTimelineRef.current = false; }, 80);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleTrackClick = (e) => {
    if (wasDraggingTimelineRef.current || timelineDragRef.current) return;
    if (!timelineRef.current || !videoRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    const targetTime = ratio * candidateDuration;
    videoRef.current.currentTime = targetTime;
    setCurrentVideoTime(targetTime);
  };

  const setStartFromPlayhead = () => {
    const t = Math.max(0, Math.min(candidateDuration - 3, Math.round(currentVideoTime * 10) / 10));
    let e = trimEnd;
    if (e <= t + 3.0) e = Math.min(candidateDuration, t + 3.0);
    else if (e - t > 60.0) e = t + 60.0;
    setTrimStart(t);
    setTrimEnd(e);
  };

  const setEndFromPlayhead = () => {
    const t = Math.min(candidateDuration, Math.max(3, Math.round(currentVideoTime * 10) / 10));
    let s = trimStart;
    if (t <= s + 3.0) s = Math.max(0, t - 3.0);
    else if (t - s > 60.0) s = t - 60.0;
    setTrimStart(s);
    setTrimEnd(t);
  };

  // Single-Pass Confirm & Create Clip
  const handleConfirmAndCreateClip = async () => {
    if (!activeClipId) return;
    if (trimEnd <= trimStart) {
      alert('End timestamp must be greater than Start timestamp.');
      return;
    }

    setIsCreatingClip(true);
    setCreateStatus('Transcribing selected range & rendering 9:16 Short (single pass)...');
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
      setIsPlaying(false);
    }

    try {
      const res = await fetch(`/api/clips/${activeClipId}/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_time: trimStart,
          end_time: trimEnd,
          face_box: faceBoxRef.current,
          game_box: gameBoxRef.current,
          title: customTitle.trim() || null
        })
      });
      if (res.ok) {
        setCreateStatus('✓ 9:16 Short created! Opening Preview & Post page...');
        if (onClipCreated) onClipCreated();
      } else {
        const err = await res.json();
        setCreateStatus(`Failed: ${err.detail || 'Error creating clip'}`);
      }
    } catch (e) {
      console.error(e);
      setCreateStatus('Connection error while creating clip');
    } finally {
      setIsCreatingClip(false);
    }
  };

  const handleDiscard = () => {
    if (videoRef.current) {
      try {
        videoRef.current.pause();
        videoRef.current.removeAttribute('src');
        videoRef.current.load();
      } catch (e) {}
    }
    if (onDiscardClip) onDiscardClip();
  };

  const combinedLogs = [...(col2?.logs || []).slice(-5), ...(col3?.logs || []).slice(-6)];

  return (
    <div className="md:col-span-2 flex flex-col h-full min-h-0 bg-[#0d0f12] font-mono select-none">
      {/* Studio Header — Fixed height, never wraps or shifts */}
      <div className="h-[43px] px-3 border-b border-[#262b34] bg-[#14171d] flex items-center justify-between shrink-0 overflow-hidden">
        <div className="flex items-center gap-3 text-[10px] text-[#88909e] whitespace-nowrap">
          <Film className="w-4 h-4 text-[#00e676] shrink-0" />
          <span className="text-red-400 font-bold">
            ■ RED: {faceBox.w}x{faceBox.h} ({faceBox.x},{faceBox.y})
          </span>
          <span className="text-blue-400 font-bold">
            ■ BLUE: {gameBox.w}x{gameBox.h} ({gameBox.x},{gameBox.y})
          </span>
          {boxSaveNotice && (
            <span className="text-[#00e676] font-bold">
              {boxSaveNotice}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 whitespace-nowrap">
          <button
            type="button"
            onClick={handleClearAll}
            disabled={isSavingBoxes}
            className="bg-[#1a1f27] hover:bg-[#262b34] text-[#88909e] hover:text-white px-2.5 py-0.5 text-[10px] font-bold border border-[#262b34] flex items-center gap-1 cursor-pointer"
            title="Clear all and reset studio state"
          >
            <RotateCcw className="w-3 h-3" />
            CLEAR ALL
          </button>
          <span className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded ${
            hasActiveCandidateVideo
              ? 'bg-[#00e676] text-black'
              : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
          }`}>
            {hasActiveCandidateVideo ? '4-MIN CLIP READY' : 'STATIC FRAME'}
          </span>
        </div>
      </div>

      <div className="flex-1 p-3 space-y-3 overflow-y-auto">
        {/* 16:9 Canvas with Always-Draggable Red (Facecam) & Blue (Gameplay) Boxes */}
        <div className="border border-[#262b34] bg-[#14171d] p-3 space-y-2.5">
          {/* 16:9 Video / Static Frame Stage — Exact edge-to-edge stream frame with zero black borders */}
          <div
            ref={canvasRef}
            onClick={hasActiveCandidateVideo ? togglePlayPause : undefined}
            style={{ aspectRatio: `${frameDim.w} / ${frameDim.h}` }}
            className="relative w-full max-w-[920px] mx-auto border-2 border-[#262b34] overflow-hidden select-none shadow-xl leading-none"
          >
            {hasActiveCandidateVideo ? (
              <video
                ref={videoRef}
                key={candidateVideoUrl}
                src={candidateVideoUrl}
                playsInline
                onLoadedMetadata={(e) => {
                  const vw = e.currentTarget.videoWidth;
                  const vh = e.currentTarget.videoHeight;
                  if (vw > 0 && vh > 0) setMediaSize({ w: vw, h: vh });
                  const dur = e.currentTarget.duration;
                  if (dur && isFinite(dur) && dur > 5) {
                    const roundedDur = Math.round(dur * 10) / 10;
                    setVideoDuration(roundedDur);
                  } else {
                    setVideoDuration(240.0);
                  }
                }}
                onTimeUpdate={(e) => setCurrentVideoTime(e.target.currentTime)}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                className="block w-full h-full object-cover pointer-events-none"
              />
            ) : fullFrameUrl ? (
              <img
                src={`${fullFrameUrl}?v=${previewVersion}`}
                alt="Static Streamer Frame"
                onLoad={(e) => {
                  const iw = e.currentTarget.naturalWidth;
                  const ih = e.currentTarget.naturalHeight;
                  if (iw > 0 && ih > 0) setMediaSize({ w: iw, h: ih });
                }}
                className="block w-full h-full object-cover pointer-events-none"
              />
            ) : (
              <div className="w-full h-full bg-[#0d0f12] flex flex-col items-center justify-center text-[#88909e] text-xs p-4 text-center">
                <span>Waiting for initial stream frame from #{channel}...</span>
                <span className="text-[10px] mt-1">You can still position and save Red & Blue boxes right now.</span>
              </div>
            )}

            {/* BLUE BOX: Gameplay (Bottom 60%) — Always Draggable */}
            <div
              onClick={(e) => e.stopPropagation()}
              onMouseDown={(e) => handleBoxMouseDown(e, 'game', 'move')}
              style={{
                left: `${(gameBox.x / frameDim.w) * 100}%`,
                top: `${(gameBox.y / frameDim.h) * 100}%`,
                width: `${(gameBox.w / frameDim.w) * 100}%`,
                height: `${(gameBox.h / frameDim.h) * 100}%`
              }}
              className={`absolute border-2 ${
                activeBox === 'game'
                  ? 'border-blue-400 bg-blue-500/20 ring-2 ring-blue-400/40'
                  : 'border-blue-500/80 bg-blue-500/10'
              } cursor-move transition-shadow`}
            >
              <div className="absolute top-0 left-0 bg-blue-600 text-white text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider flex items-center gap-1 pointer-events-none">
                <Move className="w-2.5 h-2.5" />
                BLUE: GAMEPLAY (60%) [{gameBox.w}x{gameBox.h}]
              </div>
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'game', 'nw')}
                className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 bg-blue-400 border border-white cursor-nw-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'game', 'ne')}
                className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-blue-400 border border-white cursor-ne-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'game', 'sw')}
                className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 bg-blue-400 border border-white cursor-sw-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'game', 'se')}
                className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 bg-blue-400 border border-white cursor-se-resize"
              />
            </div>

            {/* RED BOX: Facecam (Top 40%) — Always Draggable */}
            <div
              onClick={(e) => e.stopPropagation()}
              onMouseDown={(e) => handleBoxMouseDown(e, 'face', 'move')}
              style={{
                left: `${(faceBox.x / frameDim.w) * 100}%`,
                top: `${(faceBox.y / frameDim.h) * 100}%`,
                width: `${(faceBox.w / frameDim.w) * 100}%`,
                height: `${(faceBox.h / frameDim.h) * 100}%`
              }}
              className={`absolute border-2 ${
                activeBox === 'face'
                  ? 'border-red-500 bg-red-500/25 ring-2 ring-red-400/50'
                  : 'border-red-500/85 bg-red-500/15'
              } cursor-move z-10 transition-shadow`}
            >
              <div className="absolute top-0 left-0 bg-[#ff1e1e] text-white text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider flex items-center gap-1 pointer-events-none">
                <Move className="w-2.5 h-2.5" />
                RED: FACECAM (40%) [{faceBox.w}x{faceBox.h}]
              </div>
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'face', 'nw')}
                className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 bg-red-500 border border-white cursor-nw-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'face', 'ne')}
                className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-red-500 border border-white cursor-ne-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'face', 'sw')}
                className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 bg-red-500 border border-white cursor-sw-resize"
              />
              <div
                onMouseDown={(e) => handleBoxMouseDown(e, 'face', 'se')}
                className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 bg-red-500 border border-white cursor-se-resize"
              />
            </div>
          </div>

          {/* 2-Minute Video Transport & Range Slider Controls (Shown when a Peak is Processed) */}
          {hasActiveCandidateVideo ? (
            <div className="space-y-3 pt-2 border-t border-[#262b34]">
              {/* Row 1: Play / Step Navigation & Direct Start/End Controls */}
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={togglePlayPause}
                    className="bg-[#00e676] hover:bg-[#00c853] text-black font-bold px-3 py-1 text-xs flex items-center gap-1 cursor-pointer"
                  >
                    {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                    {isPlaying ? 'PAUSE' : 'PLAY'}
                  </button>
                  <button
                    type="button"
                    onClick={toggleMute}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#262b34] text-white px-2 py-1 text-xs flex items-center cursor-pointer"
                  >
                    {isMuted ? <VolumeX className="w-3.5 h-3.5 text-red-400" /> : <Volume2 className="w-3.5 h-3.5 text-[#00e676]" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => stepPlayhead(-5)}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#262b34] text-[#88909e] hover:text-white px-2 py-1 text-[11px] font-bold cursor-pointer"
                    title="Rewind 5 seconds"
                  >
                    -5s
                  </button>
                  <button
                    type="button"
                    onClick={() => stepPlayhead(-1)}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#262b34] text-[#88909e] hover:text-white px-2 py-1 text-[11px] font-bold cursor-pointer"
                    title="Back 1 second"
                  >
                    -1s
                  </button>
                  <button
                    type="button"
                    onClick={() => stepPlayhead(1)}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#262b34] text-[#88909e] hover:text-white px-2 py-1 text-[11px] font-bold cursor-pointer"
                    title="Forward 1 second"
                  >
                    +1s
                  </button>
                  <button
                    type="button"
                    onClick={() => stepPlayhead(5)}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#262b34] text-[#88909e] hover:text-white px-2 py-1 text-[11px] font-bold cursor-pointer"
                    title="Forward 5 seconds"
                  >
                    +5s
                  </button>
                  <span className="text-[#88909e] ml-1">
                    Time: <strong className="text-white">{currentVideoTime.toFixed(1)}s</strong> / {candidateDuration.toFixed(1)}s
                  </span>
                </div>

                {/* Direct Start & End Stepper Controls */}
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 bg-[#0d0f12] border border-[#262b34] px-2 py-0.5">
                    <span className="text-[10px] text-[#88909e] font-bold">START:</span>
                    <button
                      type="button"
                      onClick={() => adjustTrimStart(trimStart - 1)}
                      className="text-[#88909e] hover:text-white px-1 font-bold cursor-pointer"
                    >
                      -
                    </button>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      max="237"
                      value={trimStart}
                      onChange={(e) => adjustTrimStart(e.target.value)}
                      className="w-12 bg-transparent text-[#00e676] font-bold text-xs text-center outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => adjustTrimStart(trimStart + 1)}
                      className="text-[#88909e] hover:text-white px-1 font-bold cursor-pointer"
                    >
                      +
                    </button>
                  </div>

                  <div className="flex items-center gap-1 bg-[#0d0f12] border border-[#262b34] px-2 py-0.5">
                    <span className="text-[10px] text-[#88909e] font-bold">END:</span>
                    <button
                      type="button"
                      onClick={() => adjustTrimEnd(trimEnd - 1)}
                      className="text-[#88909e] hover:text-white px-1 font-bold cursor-pointer"
                    >
                      -
                    </button>
                    <input
                      type="number"
                      step="0.5"
                      min="3"
                      max="240"
                      value={trimEnd}
                      onChange={(e) => adjustTrimEnd(e.target.value)}
                      className="w-12 bg-transparent text-[#00e676] font-bold text-xs text-center outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => adjustTrimEnd(trimEnd + 1)}
                      className="text-[#88909e] hover:text-white px-1 font-bold cursor-pointer"
                    >
                      +
                    </button>
                  </div>

                  <span className="text-[#00e676] bg-[#00e676]/10 px-2 py-1 border border-[#00e676]/30 font-bold text-[11px]">
                    {selectedDuration.toFixed(1)}s / 60s
                  </span>
                </div>
              </div>

              {/* Row 2: Dedicated Video Scrubber Slider (Never Cut Off) */}
              <div className="bg-[#0d0f12] border border-[#262b34] px-3 py-2 space-y-1">
                <div className="flex items-center justify-between text-[10px] text-[#88909e]">
                  <span>0.0s</span>
                  <span className="text-white font-bold">
                    VIDEO POSITION: <span className="text-[#00e676]">{currentVideoTime.toFixed(1)}s</span> / {candidateDuration.toFixed(1)}s
                  </span>
                  <span>{candidateDuration.toFixed(1)}s</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={candidateDuration}
                  step={0.1}
                  value={Math.min(candidateDuration, currentVideoTime)}
                  onChange={(e) => seekVideoTo(parseFloat(e.target.value))}
                  className="w-full h-2 bg-[#262b34] accent-white cursor-pointer rounded-none"
                />
              </div>

              {/* Row 3: Clean Trim Range Bar with Thin Green Start & End Bars */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[10px] text-[#88909e] px-1">
                  <span>
                    START: <strong className="text-[#00e676]">{trimStart.toFixed(1)}s</strong>
                  </span>
                  <span className="text-yellow-400 font-bold">⚡ PEAK ({peakOffset}s)</span>
                  <span>
                    END: <strong className="text-[#00e676]">{trimEnd.toFixed(1)}s</strong>
                  </span>
                </div>

                <div
                  ref={timelineRef}
                  onMouseDown={(e) => handleTimelineMouseDown(e, 'playhead')}
                  className="relative h-10 bg-[#0d0f12] border border-[#262b34] rounded select-none cursor-pointer"
                  title="Drag thin green left/right bars to set Start & End. Drag green shaded area to slide window."
                >
                  {/* Unselected Dim Background */}
                  <div className="absolute inset-0 bg-[#0d0f12]" />

                  {/* Selected Clip Range with Thin Green Start & End Bars */}
                  <div
                    onMouseDown={(e) => handleTimelineMouseDown(e, 'move')}
                    style={{
                      left: `${Math.max(0, Math.min(100, (trimStart / candidateDuration) * 100))}%`,
                      width: `${Math.max(1, Math.min(100, (selectedDuration / candidateDuration) * 100))}%`
                    }}
                    className="absolute top-0 bottom-0 bg-[#00e676]/20 hover:bg-[#00e676]/30 border-y border-[#00e676]/70 cursor-grab active:cursor-grabbing flex items-center justify-center select-none z-10"
                  >
                    {/* Thin Green START Bar (with wide invisible grab area) */}
                    <div
                      onMouseDown={(e) => handleTimelineMouseDown(e, 'start')}
                      className="absolute left-0 top-0 bottom-0 w-4 -ml-2 cursor-ew-resize flex items-center justify-center z-20 group"
                      title={`Drag Start (${trimStart.toFixed(1)}s)`}
                    >
                      <div className="w-1.5 h-full bg-[#00e676] group-hover:bg-white shadow" />
                    </div>

                    {/* Minimal Center Duration Text */}
                    <span className="text-[10px] text-[#00e676] font-bold pointer-events-none select-none">
                      {selectedDuration.toFixed(1)}s
                    </span>

                    {/* Thin Green END Bar (with wide invisible grab area) */}
                    <div
                      onMouseDown={(e) => handleTimelineMouseDown(e, 'end')}
                      className="absolute right-0 top-0 bottom-0 w-4 -mr-2 cursor-ew-resize flex items-center justify-center z-20 group"
                      title={`Drag End (${trimEnd.toFixed(1)}s)`}
                    >
                      <div className="w-1.5 h-full bg-[#00e676] group-hover:bg-white shadow" />
                    </div>
                  </div>

                  {/* Thin Yellow Peak Line */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-yellow-400/60 pointer-events-none"
                    style={{ left: `${Math.min(100, (peakOffset / candidateDuration) * 100)}%` }}
                  />

                  {/* Thin White Playhead Line */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none z-20"
                    style={{ left: `${Math.min(100, Math.max(0, (currentVideoTime / candidateDuration) * 100))}%` }}
                  />
                </div>
              </div>

              {/* Quick Playhead Snap Buttons */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={handlePlayRange}
                    className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#00e676]/50 text-[#00e676] font-bold px-3 py-1 text-xs flex items-center gap-1 cursor-pointer"
                  >
                    <Play className="w-3 h-3 text-[#00e676]" />
                    PLAY SELECTED RANGE ({trimStart.toFixed(1)}s - {trimEnd.toFixed(1)}s)
                  </button>
                  <button
                    type="button"
                    onClick={setStartFromPlayhead}
                    className="bg-[#1a1f27] hover:bg-[#262b34] text-white border border-[#262b34] hover:border-[#00e676] px-2.5 py-1 text-[11px] font-bold cursor-pointer"
                  >
                    Set Start ({currentVideoTime.toFixed(1)}s)
                  </button>
                  <button
                    type="button"
                    onClick={setEndFromPlayhead}
                    className="bg-[#1a1f27] hover:bg-[#262b34] text-white border border-[#262b34] hover:border-[#00e676] px-2.5 py-1 text-[11px] font-bold cursor-pointer"
                  >
                    Set End ({currentVideoTime.toFixed(1)}s)
                  </button>
                </div>
              </div>

              {/* Title Input & Single-Pass Confirm & Create Clip Bar */}
              <div className="pt-2 border-t border-[#262b34] space-y-2">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] text-[#88909e] uppercase font-bold flex items-center gap-1">
                      <Edit3 className="w-3 h-3 text-[#ff1e1e]" />
                      CLIP TITLE (Auto-generated on peak process — Edit or click Regenerate AI)
                    </label>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleRegenerateTitle}
                        disabled={isGeneratingTitle}
                        className="bg-purple-600 hover:bg-purple-500 disabled:bg-[#262b34] text-white px-2 py-0.5 text-[10px] font-bold flex items-center gap-1 cursor-pointer"
                      >
                        <Sparkles className="w-2.5 h-2.5 text-yellow-300" />
                        {isGeneratingTitle ? 'GENERATING...' : 'REGENERATE AI TITLE'}
                      </button>
                      <span className="text-[10px] text-[#88909e]">{customTitle.length}/100</span>
                    </div>
                  </div>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    maxLength={100}
                    placeholder="Auto-generated viral title..."
                    className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#00e676] text-xs font-bold text-white outline-none"
                  />
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleDiscard}
                    disabled={isCreatingClip}
                    className="bg-[#262b34] hover:bg-red-950/60 hover:text-red-400 text-[#88909e] px-3 py-2 text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                    title="Remove this 2-minute video and free SSD space"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    DISCARD & FREE SPACE
                  </button>

                  <div className="flex items-center gap-2">
                    {activeClip?.clip_created && (
                      <button
                        type="button"
                        onClick={onClipCreated}
                        className="bg-[#1a1f27] hover:bg-[#262b34] border border-[#00e676]/50 text-[#00e676] px-3 py-2 text-xs font-bold cursor-pointer"
                      >
                        OPEN EXISTING SHORT &rarr;
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleConfirmAndCreateClip}
                      disabled={isCreatingClip}
                      className={`px-5 py-2.5 text-xs font-bold flex items-center gap-2 cursor-pointer ${
                        isCreatingClip
                          ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/40 cursor-wait'
                          : 'bg-[#00e676] hover:bg-[#00c853] text-black shadow-lg'
                      }`}
                    >
                      <Scissors className="w-4 h-4" />
                      {isCreatingClip
                        ? 'TRANSCRIBING RANGE & CREATING 9:16 SHORT...'
                        : `CONFIRM & CREATE CLIP (${selectedDuration.toFixed(1)}s)`}
                    </button>
                  </div>
                </div>

                {createStatus && (
                  <div className="text-xs text-[#00e676] bg-[#00e676]/10 p-2 border border-[#00e676]/30">
                    {createStatus}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-2.5 bg-[#0d0f12] border border-[#262b34] flex items-center justify-between text-xs text-[#88909e]">
              <span>
                Static frame active for <strong className="text-white">#{channel}</strong>. Position the Red & Blue boxes anytime — they are saved automatically for this streamer.
              </span>
              <span className="text-[#00e676] font-bold">
                Click PROCESS on any Peak in Column 1 to load the 4-minute 16:9 clip &rarr;
              </span>
            </div>
          )}
        </div>

        {/* Compact Studio Activity Logs */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1 flex items-center gap-1">
            <Terminal className="w-3 h-3" />
            STUDIO & PIPELINE LOGS
          </div>
          <div className="h-20 overflow-y-auto text-[10px] space-y-0.5 bg-[#0d0f12] p-1.5 border border-[#262b34] text-[#88909e]">
            {combinedLogs.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap">{l}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
