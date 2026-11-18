import React, { useState } from 'react';
import { ScanFace, LayoutTemplate, Terminal, Image as ImageIcon, Sliders, CheckCircle2 } from 'lucide-react';

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
  const currentMode = data?.facecam_mode || 'AUTO';
  const ruleApplied = data?.rule_applied || 'RULE 1: FIT BOX (1080x768)';
  const hasBackground = data?.has_background !== false;

  const [togglingMode, setTogglingMode] = useState(false);

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
    if (s === 'LOCKED' || s === 'OK') return 'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/30';
    if (s.includes('DETECTING') || s.includes('FALLBACK')) return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30';
    return 'bg-[#262b34] text-[#88909e]';
  };

  return (
    <div className="flex flex-col h-full min-h-0 border-r border-[#262b34] bg-[#0d0f12]">
      {/* Column Title */}
      <div className="p-3 border-b border-[#262b34] bg-[#14171d] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <ScanFace className="w-4 h-4 text-blue-400" />
          <span className="font-bold text-xs uppercase tracking-wider text-white">
            COLUMN 2: FACECAM & FRAMING
          </span>
        </div>
        <span className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded ${getStatusBg(status)}`}>
          {status}
        </span>
      </div>

      <div className="p-3 space-y-3 flex-1 min-h-0 overflow-y-auto">
        {/* Core Metrics Grid */}
        <div className="grid grid-cols-3 gap-2">
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Face Pos (X, Y)</div>
            <div className="text-base font-bold font-mono text-white">({box.x}, {box.y})</div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Size (W x H)</div>
            <div className="text-base font-bold font-mono text-white">{box.w}x{box.h}</div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Confidence</div>
            <div className={`text-base font-bold font-mono ${usingFallback ? 'text-yellow-400' : 'text-[#00e676]'}`}>
              {edgeConf > 0 ? `${edgeConf.toFixed(0)}%` : 'FALLBACK'}
            </div>
          </div>
        </div>

        {/* Dynamic Framing Rules Selector */}
        <div className="border border-[#262b34] bg-[#14171d] p-2.5 space-y-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-blue-400">
              <Sliders className="w-3.5 h-3.5" />
              FACECAM FRAMING RULE
            </span>
            <span className="text-[10px] font-mono font-bold text-white bg-[#0d0f12] px-1.5 py-0.5 border border-[#262b34]">
              {ruleApplied}
            </span>
          </div>

          {/* Mode Selector Buttons */}
          <div className="grid grid-cols-3 gap-1.5 text-[11px] font-mono">
            <button
              onClick={() => handleModeChange('AUTO')}
              disabled={togglingMode}
              className={`py-1 px-2 border text-center font-bold transition-none ${
                currentMode === 'AUTO'
                  ? 'border-blue-400 bg-blue-500/20 text-blue-300'
                  : 'border-[#262b34] bg-[#0d0f12] text-[#88909e] hover:text-white'
              }`}
            >
              AUTO-DETECT
            </button>
            <button
              onClick={() => handleModeChange('BACKGROUND')}
              disabled={togglingMode}
              className={`py-1 px-1.5 border text-center font-bold transition-none ${
                currentMode === 'BACKGROUND'
                  ? 'border-[#00e676] bg-[#00e676]/20 text-[#00e676]'
                  : 'border-[#262b34] bg-[#0d0f12] text-[#88909e] hover:text-white'
              }`}
            >
              BOX (WITH BG)
            </button>
            <button
              onClick={() => handleModeChange('NO_BACKGROUND')}
              disabled={togglingMode}
              className={`py-1 px-1.5 border text-center font-bold transition-none ${
                currentMode === 'NO_BACKGROUND'
                  ? 'border-[#ff1e1e] bg-[#ff1e1e]/20 text-[#ff1e1e]'
                  : 'border-[#262b34] bg-[#0d0f12] text-[#88909e] hover:text-white'
              }`}
            >
              CUTOUT (NO BG)
            </button>
          </div>

          {/* Rule Description Note */}
          <div className="text-[10px] font-mono text-[#88909e] bg-[#0d0f12] p-1.5 border border-[#262b34]/60">
            {hasBackground ? (
              <span className="text-white flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3 text-[#00e676] shrink-0" />
                <span><strong>Primary Rule 1:</strong> Facecam with border/background: Scaled to measure just over 1080x768 (edge-to-edge).</span>
              </span>
            ) : (
              <span className="text-white flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3 text-yellow-400 shrink-0" />
                <span><strong>Secondary Rule 2:</strong> Cutout (no border/bg): Face sized to 50% of 40% window (384px) & centered.</span>
              </span>
            )}
          </div>
        </div>

        {/* 40/60 Split Layout Preview */}
        <div className="border border-[#262b34] bg-[#14171d] p-3">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1">
              <LayoutTemplate className="w-3 h-3 text-blue-400" />
              40/60 CANVAS COMPOSITION (1080 x 1920)
            </span>
            {hasPreview && (
              <span className="text-[9px] text-[#00e676] font-mono flex items-center gap-1">
                <ImageIcon className="w-2.5 h-2.5" /> LIVE CROPS CAPTURED
              </span>
            )}
          </div>

          <div className="flex gap-3 items-center">
            {/* Visual 9:16 Preview Box */}
            <div className="w-28 h-48 border-2 border-[#ff1e1e] bg-black flex flex-col shrink-0 overflow-hidden relative shadow-lg">
              {/* Top 40% Facecam Slot */}
              <div className="h-[40%] border-b border-blue-400/50 bg-[#0d0f12] overflow-hidden relative flex items-center justify-center">
                {hasPreview && facecamUrl ? (
                  <img
                    src={`${facecamUrl}?v=${previewVersion}`}
                    alt="Facecam Crop"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center p-1">
                    <div className="text-[8px] text-blue-400 font-bold uppercase">40% Facecam</div>
                    <div className="text-[7px] text-[#88909e]">1080x768</div>
                  </div>
                )}
                <span className="absolute top-0.5 left-0.5 bg-black/70 px-1 text-[7px] text-blue-400 font-bold uppercase">
                  Top 40%
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
                    <div className="text-[8px] text-[#00e676] font-bold uppercase">60% Gameplay</div>
                    <div className="text-[7px] text-[#88909e]">1080x1152</div>
                  </div>
                )}
                <span className="absolute top-0.5 left-0.5 bg-black/70 px-1 text-[7px] text-[#00e676] font-bold uppercase">
                  Bot 60%
                </span>
              </div>
            </div>

            {/* Geometry Details */}
            <div className="text-[11px] font-mono space-y-1.5 text-[#88909e]">
              <div><strong className="text-white">Canvas:</strong> 9:16 Vertical (1080x1920)</div>
              <div><strong className="text-white">Top 40%:</strong> {ruleApplied}</div>
              <div><strong className="text-white">Facecam Window:</strong> 1080 x 768 px</div>
              <div><strong className="text-white">Target Face:</strong> {hasBackground ? 'Natural Fit (No Zoom Tank)' : '384px (50% Window)'}</div>
              <div><strong className="text-white">Bottom 60%:</strong> Centered Gameplay (1080x1152)</div>
              <div><strong className="text-white">Detector:</strong> YuNet Deep Neural Network</div>
              <div><strong className="text-white">Lock State:</strong> {usingFallback ? 'FALLBACK' : 'AI LOCKED'}</div>
            </div>
          </div>
        </div>

        {/* Framing Log */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center gap-1">
            <Terminal className="w-3 h-3" />
            FRAMING & CV2 LOGS
          </div>
          <div className="h-44 overflow-y-auto text-[10px] font-mono space-y-0.5 bg-[#0d0f12] p-1.5 border border-[#262b34] text-[#88909e]">
            {logs.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap">{l}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
