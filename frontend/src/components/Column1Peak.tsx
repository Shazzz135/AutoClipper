import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  MessageSquare,
  ListFilter,
  Terminal,
  Play,
  Volume2,
  Flame,
  Trash2,
  Sliders,
  Users,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Radio,
  Film,
  Search,
  RefreshCw,
  Clock,
  ExternalLink
} from 'lucide-react';

export default function Column1Peak({ data, activeClipId, state }) {
  const status = data?.status || 'INITIALIZING';
  const velocity = data?.msg_velocity || 0;
  const baseline = data?.baseline_velocity || 0;
  const zScore = data?.current_z_score || 0;
  const recentChat = data?.recent_chat || [];
  const peaks = data?.detected_peaks || [];
  const logs = data?.logs || [];
  const [processingId, setProcessingId] = useState(null);
  const [deletedPeakIds, setDeletedPeakIds] = useState(new Set());

  // Mode Toggle: 'LIVE' vs 'VOD'
  const [sourceMode, setSourceMode] = useState('LIVE');
  const [vodUrlInput, setVodUrlInput] = useState('');
  const [isScanningVod, setIsScanningVod] = useState(false);
  const [vodScanData, setVodScanData] = useState(null);
  const [vodScanError, setVodScanError] = useState(null);
  const [processingVodPeakId, setProcessingVodPeakId] = useState(null);

  // Dynamic peak calibration state
  const calib = state?.peak_calibration || {};
  const isDynamic = calib.dynamic_mode !== false;
  const streamerTier = calib.streamer_tier || 'AUTO';
  const activeTier = calib.active_tier || 'MEGA';
  const sensitivity = calib.sensitivity || 'NORMAL';
  const baseZ = calib.base_z || 3.0;
  const baseVelocity = calib.base_velocity || 10.0;
  const reqVelocity = calib.req_velocity || 10.0;
  const reqZScore = calib.req_z_score || 3.0;
  const audioBoost = calib.audio_boost !== false;
  const hypeBoost = calib.hype_boost !== false;
  const viewers = state?.stream_viewers || 0;
  const hypeDensity = state?.chat_hype_density || 0;

  const [showConfig, setShowConfig] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  const fetchVodStatus = async () => {
    try {
      const res = await fetch('/api/vod/status');
      if (res.ok) {
        const data = await res.json();
        setVodScanData(data);
        if (data.is_scanning) {
          setIsScanningVod(true);
        } else {
          setIsScanningVod(false);
        }
      }
    } catch (e) {
      console.error('Failed to fetch VOD status:', e);
    }
  };

  useEffect(() => {
    fetchVodStatus();
  }, [sourceMode]);

  // Polling every 2s while VOD scan is actively running
  useEffect(() => {
    if (!isScanningVod) return;
    const interval = setInterval(async () => {
      await fetchVodStatus();
    }, 2000);
    return () => clearInterval(interval);
  }, [isScanningVod]);

  const handleStartVodScan = async (e) => {
    if (e) e.preventDefault();
    if (!vodUrlInput.trim()) return;
    setIsScanningVod(true);
    setVodScanError(null);
    try {
      const res = await fetch('/api/vod/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vod_url: vodUrlInput.trim() })
      });
      if (!res.ok) {
        const err = await res.json();
        setVodScanError(err.detail || 'Failed to start VOD scan');
        setIsScanningVod(false);
      } else {
        await fetchVodStatus();
      }
    } catch (err) {
      console.error('Scan request error:', err);
      setVodScanError(String(err));
      setIsScanningVod(false);
    }
  };

  const handleProcessVodPeak = async (peak) => {
    setProcessingVodPeakId(peak.peak_id);
    try {
      const res = await fetch('/api/vod/process_peak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vod_url: vodScanData?.vod_info?.url || vodUrlInput.trim(),
          peak: peak
        })
      });
      if (!res.ok) {
        let errMsg = 'Could not process peak';
        try {
          const err = await res.json();
          errMsg = err.detail || errMsg;
        } catch (_) {
          errMsg = await res.text();
        }
        alert(errMsg);
      }
    } catch (err) {
      console.error('Process VOD peak error:', err);
    } finally {
      setProcessingVodPeakId(null);
    }
  };

  const handleClearVod = async () => {
    try {
      await fetch('/api/vod/clear', { method: 'POST' });
      setVodScanData(null);
      setVodUrlInput('');
      setVodScanError(null);
    } catch (e) {}
  };

  const updateSetting = async (key, val) => {
    setSavingSettings(true);
    try {
      await fetch('/api/settings/peak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: val })
      });
    } catch (err) {
      console.error('Failed to update peak calibration:', err);
    } finally {
      setSavingSettings(false);
    }
  };

  // Automatically clear processingId if that peak is no longer in queue or finished processing
  useEffect(() => {
    if (processingId) {
      const stillProcessing = peaks.some(p => p.peak_id === processingId && p.status === 'PROCESSING');
      if (!stillProcessing) {
        setProcessingId(null);
      }
    }
  }, [peaks, processingId]);

  const handleProcessPeak = async (peakId) => {
    setProcessingId(peakId);
    try {
      await fetch(`/api/peaks/${peakId}/process`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to process peak:', err);
      setProcessingId(null);
    }
  };

  const handleDeletePeak = async (e, peakId) => {
    e.stopPropagation();
    // Optimistically hide from UI immediately
    setDeletedPeakIds(prev => new Set([...prev, peakId]));
    if (processingId === peakId) setProcessingId(null);

    try {
      const res = await fetch(`/api/peaks/${peakId}`, { method: 'DELETE' });
      if (!res.ok) {
        // Fallback POST endpoint
        await fetch(`/api/peaks/${peakId}/delete`, { method: 'POST' });
      }
    } catch (err) {
      console.error('Failed to delete peak:', err);
    }
  };

  const handleClearAllPeaks = async () => {
    if (window.confirm('Clear all queued peak spikes?')) {
      const allIds = peaks.map(p => p.peak_id);
      setDeletedPeakIds(new Set(allIds));
      setProcessingId(null);

      try {
        const res = await fetch('/api/peaks', { method: 'DELETE' });
        if (!res.ok) {
          await fetch('/api/peaks/clear', { method: 'POST' });
        }
      } catch (err) {
        console.error('Failed to clear peaks:', err);
      }
    }
  };

  const getStatusBg = (s) => {
    if (s.includes('SPIKE') || s.includes('PROCESSING')) return 'bg-[#ff1e1e] text-white';
    if (s === 'MONITORING' || s === 'OK') return 'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/30';
    return 'bg-[#262b34] text-[#88909e]';
  };

  const visiblePeaks = peaks.filter(p => !deletedPeakIds.has(p.peak_id));

  return (
    <div className="flex flex-col h-full min-h-0 border-r border-[#262b34] bg-[#0d0f12]">
      {/* Column Title */}
      <div className="p-3 border-b border-[#262b34] bg-[#14171d] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-[#ff1e1e]" />
          <span className="font-bold text-xs uppercase tracking-wider text-white">
            COLUMN 1: PEAK DETECTION
          </span>
        </div>
        <span className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded ${getStatusBg(status)}`}>
          {status}
        </span>
      </div>

      {/* Detection Source Mode Switcher: LIVE STREAM vs ENDED STREAM (VOD) */}
      <div className="flex border-b border-[#262b34] bg-[#0d0f12] text-xs font-mono shrink-0">
        <button
          type="button"
          onClick={() => setSourceMode('LIVE')}
          className={`flex-1 py-1.5 px-3 flex items-center justify-center gap-1.5 font-bold transition-none border-r border-[#262b34] ${
            sourceMode === 'LIVE'
              ? 'bg-[#14171d] text-[#00e676] border-b-2 border-b-[#00e676]'
              : 'text-[#88909e] hover:text-white bg-[#0d0f12]'
          }`}
        >
          <Radio className={`w-3.5 h-3.5 ${state?.stream_online ? 'text-[#00e676] animate-pulse' : 'text-[#88909e]'}`} />
          <span>LIVE STREAM</span>
        </button>

        <button
          type="button"
          onClick={() => setSourceMode('VOD')}
          className={`flex-1 py-1.5 px-3 flex items-center justify-center gap-1.5 font-bold transition-none ${
            sourceMode === 'VOD'
              ? 'bg-[#14171d] text-[#ff1e1e] border-b-2 border-b-[#ff1e1e]'
              : 'text-[#88909e] hover:text-white bg-[#0d0f12]'
          }`}
        >
          <Film className="w-3.5 h-3.5 text-[#ff1e1e]" />
          <span>ENDED STREAM (VOD)</span>
        </button>
      </div>

      <div className="p-3 space-y-3 flex-1 min-h-0 overflow-y-auto">
        {sourceMode === 'LIVE' ? (
          <>
            {/* Dynamic Multi-Factor Peak Calibration Card */}
        <div className="border border-[#262b34] bg-[#14171d] p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-mono font-bold text-white">
              <Sliders className="w-3.5 h-3.5 text-yellow-400" />
              <span>DYNAMIC PEAK CALIBRATION</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`px-1.5 py-0.5 text-[9px] font-mono font-bold rounded ${
                isDynamic ? 'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/30' : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
              }`}>
                {isDynamic ? 'AUTO-ADAPTIVE' : 'MANUAL'}
              </span>
              <button
                type="button"
                onClick={() => setShowConfig(!showConfig)}
                className="text-[10px] text-[#88909e] hover:text-white p-0.5 bg-[#0d0f12] border border-[#262b34] px-1.5 py-0.5 font-mono flex items-center gap-1 transition-none"
                title="Adjust dynamic peak requirements"
              >
                {showConfig ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {showConfig ? 'HIDE' : 'ADJUST'}
              </button>
            </div>
          </div>

          {/* Live Multi-Factor Status Bar */}
          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono bg-[#0d0f12] p-1.5 border border-[#262b34]">
            <div className="flex items-center justify-between px-1">
              <span className="text-[#88909e] flex items-center gap-1">
                <Users className="w-3 h-3 text-blue-400" />
                Streamer Tier:
              </span>
              <span className="font-bold text-white">
                {activeTier} <span className="text-[9px] text-[#88909e]">({viewers > 0 ? `~${viewers >= 1000 ? `${(viewers/1000).toFixed(1)}k` : viewers} viewers` : 'Live'})</span>
              </span>
            </div>

            <div className="flex items-center justify-between px-1">
              <span className="text-[#88909e] flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-yellow-400" />
                Hype Density:
              </span>
              <span className={`font-bold ${hypeDensity >= 0.5 ? 'text-[#00e676]' : 'text-white'}`}>
                {Math.round(hypeDensity * 100)}% {hypeDensity >= 0.5 && '🔥'}
              </span>
            </div>

            <div className="flex items-center justify-between px-1">
              <span className="text-[#88909e]">Required Vel:</span>
              <span className={`font-bold ${velocity >= reqVelocity ? 'text-[#ff1e1e]' : 'text-[#88909e]'}`}>
                &ge; {reqVelocity} msg/s
              </span>
            </div>

            <div className="flex items-center justify-between px-1">
              <span className="text-[#88909e]">Required Z:</span>
              <span className={`font-bold ${zScore >= reqZScore ? 'text-[#ff1e1e]' : 'text-[#88909e]'}`}>
                &ge; {reqZScore}
              </span>
            </div>
          </div>

          {/* Expandable Calibration Controls */}
          {showConfig && (
            <div className="pt-2 border-t border-[#262b34] space-y-2.5 text-xs font-mono">
              {/* Mode Toggle */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-[#88909e] uppercase">Calibration Mode</span>
                <div className="flex gap-1 text-[10px]">
                  <button
                    onClick={() => updateSetting('dynamic_mode', true)}
                    className={`px-2 py-0.5 border ${
                      isDynamic ? 'bg-[#00e676]/20 border-[#00e676] text-[#00e676] font-bold' : 'bg-[#0d0f12] border-[#262b34] text-[#88909e]'
                    }`}
                  >
                    DYNAMIC ADAPTIVE
                  </button>
                  <button
                    onClick={() => updateSetting('dynamic_mode', false)}
                    className={`px-2 py-0.5 border ${
                      !isDynamic ? 'bg-yellow-500/20 border-yellow-500 text-yellow-400 font-bold' : 'bg-[#0d0f12] border-[#262b34] text-[#88909e]'
                    }`}
                  >
                    MANUAL FIXED
                  </button>
                </div>
              </div>

              {/* Streamer Tier Selector */}
              <div>
                <label className="text-[10px] text-[#88909e] uppercase block mb-1">Streamer Scale / Audience Tier</label>
                <div className="grid grid-cols-5 gap-1 text-[9px] text-center">
                  {['AUTO', 'MEGA', 'LARGE', 'MEDIUM', 'SMALL'].map(t => (
                    <button
                      key={t}
                      onClick={() => updateSetting('streamer_tier', t)}
                      className={`p-1 border uppercase font-bold ${
                        streamerTier === t ? 'border-[#ff1e1e] bg-[#ff1e1e]/20 text-white' : 'border-[#262b34] bg-[#0d0f12] text-[#88909e] hover:text-white'
                      }`}
                      title={t === 'AUTO' ? 'Auto-detect from live viewer count & baseline' : `${t} streamer tier`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sensitivity Selector */}
              <div>
                <label className="text-[10px] text-[#88909e] uppercase block mb-1">Detection Sensitivity</label>
                <div className="grid grid-cols-3 gap-1 text-center">
                  {[
                    { id: 'LOW', label: 'LOW (Strict)' },
                    { id: 'NORMAL', label: 'BALANCED' },
                    { id: 'HIGH', label: 'HIGH (Sensitive)' }
                  ].map(s => (
                    <button
                      key={s.id}
                      onClick={() => updateSetting('sensitivity', s.id)}
                      className={`p-1 border uppercase font-bold text-[9px] ${
                        sensitivity === s.id ? 'border-[#00e676] bg-[#00e676]/20 text-[#00e676]' : 'border-[#262b34] bg-[#0d0f12] text-[#88909e] hover:text-white'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sliders: Base Z-Score & Min Velocity */}
              <div className="space-y-1.5 bg-[#0d0f12] p-2 border border-[#262b34]">
                <div>
                  <div className="flex justify-between text-[10px] text-[#88909e] mb-0.5">
                    <span>Base Z-Score Threshold:</span>
                    <strong className="text-white">{baseZ}</strong>
                  </div>
                  <input
                    type="range"
                    min="1.5"
                    max="4.5"
                    step="0.1"
                    value={baseZ}
                    onChange={(e) => updateSetting('base_z', parseFloat(e.target.value))}
                    className="w-full accent-[#ff1e1e] cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] text-[#88909e] mb-0.5">
                    <span>Base Surge Velocity:</span>
                    <strong className="text-white">{baseVelocity} msg/s</strong>
                  </div>
                  <input
                    type="range"
                    min="1.0"
                    max="25.0"
                    step="0.5"
                    value={baseVelocity}
                    onChange={(e) => updateSetting('base_velocity', parseFloat(e.target.value))}
                    className="w-full accent-[#ff1e1e] cursor-pointer"
                  />
                </div>
              </div>

              {/* Multi-Factor Boost Toggles */}
              <div className="flex flex-col gap-1.5 pt-1 border-t border-[#262b34] text-[10px]">
                <label className="flex items-center gap-1.5 cursor-pointer text-[#e1e4ea]">
                  <input
                    type="checkbox"
                    checked={audioBoost}
                    onChange={(e) => updateSetting('audio_boost', e.target.checked)}
                    className="accent-[#00e676]"
                  />
                  <span>Audio Scream Boost (-0.35 Z on loud shout/scream)</span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer text-[#e1e4ea]">
                  <input
                    type="checkbox"
                    checked={hypeBoost}
                    onChange={(e) => updateSetting('hype_boost', e.target.checked)}
                    className="accent-[#00e676]"
                  />
                  <span>Chat Hype & Emotes Boost (-0.25 Z on &ge;50% emote spam)</span>
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Core Metrics Grid */}
        <div className="grid grid-cols-3 gap-2">
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Velocity</div>
            <div className={`text-lg font-bold font-mono ${velocity >= reqVelocity ? 'text-[#ff1e1e]' : 'text-white'}`}>
              {velocity} <span className="text-[10px] font-normal text-[#88909e]">/ &ge;{reqVelocity}</span>
            </div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Baseline</div>
            <div className="text-lg font-bold font-mono text-[#88909e]">{baseline} <span className="text-[10px] font-normal">msg/s</span></div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Z-Score</div>
            <div className={`text-lg font-bold font-mono ${zScore >= reqZScore ? 'text-[#ff1e1e]' : 'text-white'}`}>
              {zScore} <span className="text-[10px] font-normal text-[#88909e]">/ &ge;{reqZScore}</span>
            </div>
          </div>
        </div>

        {/* Detected Peak Spikes Queue */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Flame className="w-3.5 h-3.5 text-[#ff1e1e]" />
              QUEUED PEAK SPIKES ({visiblePeaks.length}/10)
            </span>
            <div className="flex items-center gap-2">
              {visiblePeaks.length > 0 && (
                <button
                  onClick={handleClearAllPeaks}
                  className="text-[9px] text-[#88909e] hover:text-red-400 uppercase font-mono flex items-center gap-0.5 px-1 py-0.5 bg-[#0d0f12] border border-[#262b34] hover:border-red-500/40"
                  title="Clear all peaks from the queue"
                >
                  <Trash2 className="w-2.5 h-2.5" />
                  CLEAR ALL
                </button>
              )}
              <span className="text-[9px] text-[#88909e]">SELECT TO PROCESS</span>
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto text-[11px] font-mono space-y-2 bg-[#0d0f12] p-2 border border-[#262b34]">
            {visiblePeaks.length === 0 ? (
              <div className="text-[#88909e] italic p-3 text-center">
                Waiting for hype spikes (&ge;{reqVelocity} msg/s, Z&ge;{reqZScore})...
              </div>
            ) : (
              visiblePeaks.map((p, i) => {
                const isProcessing = processingId === p.peak_id || p.status === 'PROCESSING';
                return (
                  <div
                    key={i}
                    className="p-2 border border-[#262b34] bg-[#14171d] space-y-1.5 hover:border-[#ff1e1e]/60 transition-none"
                  >
                    {/* Top Row: Peak ID, Time, Velocity & Action Buttons */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <strong className="text-white font-bold text-xs">{p.peak_id}</strong>
                        <span className="text-[10px] text-[#88909e]">[{p.time}]</span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-[#ff1e1e]/20 text-[#ff1e1e] font-bold border border-[#ff1e1e]/30">
                          {p.velocity} msg/s
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => handleProcessPeak(p.peak_id)}
                          disabled={isProcessing || Boolean(activeClipId) || Boolean(state?.is_processing)}
                          title={
                            state?.is_processing
                              ? 'A clip is currently rendering. Only 1 clip at a time permitted.'
                              : activeClipId
                              ? 'Only 1 clip at a time. Review or discard current clip first.'
                              : isProcessing
                              ? 'Processing this clip...'
                              : 'Process this peak spike'
                          }
                          className={`px-2.5 py-1 text-[10px] font-bold font-mono uppercase flex items-center gap-1 transition-none ${
                            isProcessing || activeClipId || state?.is_processing
                              ? 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
                              : 'bg-[#ff1e1e] hover:bg-[#d01818] text-white cursor-pointer'
                          }`}
                        >
                          <Play className="w-2.5 h-2.5" />
                          {isProcessing || p.status === 'PROCESSING'
                            ? 'PROCESSING'
                            : (activeClipId || state?.is_processing)
                            ? '1 AT A TIME'
                            : 'PROCESS'}
                        </button>

                        <button
                          onClick={(e) => handleDeletePeak(e, p.peak_id)}
                          title="Delete / dismiss this peak from queue"
                          className="p-1 bg-[#0d0f12] hover:bg-red-950/60 hover:text-red-400 text-[#88909e] border border-[#262b34]"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>

                    {/* Bottom Row: Clear, Unbroken Metrics Badges */}
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                      <span className="bg-[#0d0f12] text-cyan-300 px-1.5 py-0.5 border border-[#262b34] font-bold">
                        Z: {p.z_score}
                      </span>
                      <span className="bg-[#0d0f12] text-yellow-400 px-1.5 py-0.5 border border-[#262b34] flex items-center gap-1">
                        <Volume2 className="w-2.5 h-2.5" />
                        {p.loudness_db}dB ({p.intensity || 'NORMAL'})
                      </span>
                      {p.streamer_tier && (
                        <span className="bg-[#0d0f12] text-blue-400 px-1.5 py-0.5 border border-[#262b34] font-bold">
                          Tier: {p.streamer_tier}
                        </span>
                      )}
                      {p.hype_density !== undefined && (
                        <span className="bg-[#0d0f12] text-[#00e676] px-1.5 py-0.5 border border-[#262b34]">
                          {p.hype_density}% Hype
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Live Chat Stream */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center gap-1">
            <MessageSquare className="w-3 h-3" />
            LIVE CHAT FEED
          </div>
          <div className="h-28 overflow-y-auto text-[11px] font-mono space-y-1 bg-[#0d0f12] p-1.5 border border-[#262b34]">
            {recentChat.length === 0 ? (
              <div className="text-[#88909e] italic">Waiting for incoming messages...</div>
            ) : (
              recentChat.map((c, i) => (
                <div key={i} className="truncate">
                  <span className="text-[#88909e] mr-1">[{c.time}]</span>
                  <span className="text-blue-400 font-semibold mr-1">{c.user}:</span>
                  <span className="text-[#e1e4ea]">{c.msg}</span>
                </div>
              ))
            )}
          </div>
        </div>
          </>
        ) : (
          /* ========================================================
             ENDED STREAM / VOD SCAN LAYOUT
             ======================================================== */
          <>
            {/* VOD URL Input & Scan Controller Card */}
            <div className="border border-[#262b34] bg-[#14171d] p-3 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-white flex items-center gap-1.5 uppercase">
                  <Film className="w-3.5 h-3.5 text-[#ff1e1e]" />
                  Twitch VOD Link & Scan
                </span>
                {vodScanData?.vod_info && (
                  <button
                    type="button"
                    onClick={handleClearVod}
                    className="text-[9px] font-mono text-[#88909e] hover:text-red-400 px-1.5 py-0.5 border border-[#262b34] bg-[#0d0f12] cursor-pointer"
                  >
                    CLEAR VOD
                  </button>
                )}
              </div>

              <form onSubmit={handleStartVodScan} className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    placeholder="Paste Twitch VOD URL (e.g. https://www.twitch.tv/videos/2933280749)..."
                    value={vodUrlInput}
                    onChange={(e) => setVodUrlInput(e.target.value)}
                    disabled={isScanningVod}
                    className="flex-1 bg-[#0d0f12] border border-[#262b34] focus:border-[#ff1e1e] p-2 text-xs font-mono text-white outline-none"
                  />
                  <button
                    type="submit"
                    disabled={isScanningVod || !vodUrlInput.trim()}
                    className={`px-3 py-2 text-xs font-mono font-bold flex items-center gap-1.5 transition-none shrink-0 ${
                      isScanningVod || !vodUrlInput.trim()
                        ? 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
                        : 'bg-[#ff1e1e] hover:bg-[#d01818] text-white cursor-pointer'
                    }`}
                  >
                    {isScanningVod ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        SCANNING...
                      </>
                    ) : (
                      <>
                        <Search className="w-3.5 h-3.5" />
                        SCAN VOD
                      </>
                    )}
                  </button>
                </div>
              </form>

              {/* Live Scan Progress Bar */}
              {isScanningVod && (
                <div className="space-y-1 bg-[#0d0f12] p-2 border border-[#262b34]">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-yellow-400 font-bold flex items-center gap-1">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      {vodScanData?.status_text || 'Scanning VOD chat replay...'}
                    </span>
                    <span className="text-white font-bold">{vodScanData?.progress_pct || 15}%</span>
                  </div>
                  <div className="w-full bg-[#1e222a] h-1.5 overflow-hidden">
                    <div
                      className="bg-[#ff1e1e] h-full transition-all duration-300"
                      style={{ width: `${vodScanData?.progress_pct || 15}%` }}
                    />
                  </div>
                </div>
              )}

              {vodScanError && (
                <div className="p-2 bg-red-950/40 border border-red-500/50 text-red-200 text-xs font-mono">
                  ⚠️ {vodScanError}
                </div>
              )}

              {/* VOD Metadata Card */}
              {vodScanData?.vod_info && (
                <div className="bg-[#0d0f12] p-2 border border-[#262b34] flex gap-2.5 items-start">
                  {vodScanData.vod_info.thumbnail && (
                    <img
                      src={vodScanData.vod_info.thumbnail}
                      alt="VOD Thumb"
                      className="w-24 h-14 object-cover border border-[#262b34] shrink-0"
                    />
                  )}
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="font-bold text-xs text-white truncate" title={vodScanData.vod_info.title}>
                      {vodScanData.vod_info.title}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-[#88909e]">
                      <span className="text-blue-400 font-bold">#{vodScanData.vod_info.streamer}</span>
                      <span>|</span>
                      <span className="flex items-center gap-0.5 text-white">
                        <Clock className="w-2.5 h-2.5 text-yellow-400" />
                        {vodScanData.vod_info.duration_display}
                      </span>
                      <span>|</span>
                      <a
                        href={vodScanData.vod_info.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:underline flex items-center gap-0.5"
                      >
                        Open VOD <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Discovered Top Moments Queue (1 at a Time) */}
            <div className="border border-[#262b34] bg-[#14171d] p-2">
              <div className="text-[10px] font-bold text-[#88909e] uppercase mb-2 flex items-center justify-between">
                <span className="flex items-center gap-1 text-white">
                  <Flame className="w-3.5 h-3.5 text-[#ff1e1e]" />
                  TOP MOMENTS ({vodScanData?.peaks?.length || 0}) — 1 AT A TIME
                </span>
                <span className="text-[9px] text-[#88909e]">RANKED BY HYPE</span>
              </div>

              <div className="max-h-96 overflow-y-auto text-[11px] font-mono space-y-2 bg-[#0d0f12] p-2 border border-[#262b34]">
                {!vodScanData?.peaks || vodScanData.peaks.length === 0 ? (
                  <div className="text-[#88909e] italic p-6 text-center space-y-2">
                    <Film className="w-6 h-6 mx-auto text-[#88909e]/60" />
                    <div className="text-xs text-white font-bold">No VOD scanned yet</div>
                    <div className="text-[10px] text-[#88909e] max-w-xs mx-auto">
                      Paste a Twitch VOD link above and click <strong>SCAN VOD</strong>. Top excitement moments across the entire stream will be discovered and queued here for one-by-one processing.
                    </div>
                  </div>
                ) : (
                  vodScanData.peaks.map((p, i) => {
                    const isProcessing = processingVodPeakId === p.peak_id || state?.is_processing;
                    return (
                      <div
                        key={p.peak_id || i}
                        className="p-2 border border-[#262b34] bg-[#14171d] space-y-1.5 hover:border-[#ff1e1e]/60"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-1.5 py-0.5 bg-[#ff1e1e] text-white text-[10px] font-bold">
                              #{p.rank}
                            </span>
                            <strong className="text-white font-bold text-xs flex items-center gap-1">
                              <Clock className="w-3 h-3 text-yellow-400" />
                              {p.time_display}
                            </strong>
                            <span className="text-[10px] px-1.5 py-0.5 bg-[#ff1e1e]/20 text-[#ff1e1e] font-bold border border-[#ff1e1e]/30">
                              {p.velocity} msg/s
                            </span>
                            <span className="bg-[#0d0f12] text-cyan-300 px-1.5 py-0.5 border border-[#262b34] text-[10px] font-bold">
                              Z: {p.z_score}
                            </span>
                            {p.hype_density !== undefined && (
                              <span className="bg-[#0d0f12] text-[#00e676] px-1.5 py-0.5 border border-[#262b34] text-[10px]">
                                {p.hype_density}% Hype
                              </span>
                            )}
                          </div>

                          <button
                            type="button"
                            onClick={() => handleProcessVodPeak(p)}
                            disabled={isProcessing || Boolean(activeClipId)}
                            title={
                              state?.is_processing
                                ? 'A clip is currently rendering. Only 1 clip at a time permitted.'
                                : activeClipId
                                ? 'Only 1 clip at a time. Review or discard current clip first.'
                                : isProcessing
                                ? 'Extracting & rendering this moment...'
                                : 'Process this peak clip'
                            }
                            className={`px-3 py-1 text-[10px] font-bold font-mono uppercase flex items-center gap-1 shrink-0 cursor-pointer ${
                              isProcessing || activeClipId
                                ? 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
                                : 'bg-[#ff1e1e] hover:bg-[#d01818] text-white'
                            }`}
                          >
                            <Play className="w-2.5 h-2.5" />
                            {processingVodPeakId === p.peak_id
                              ? 'SLICING...'
                              : (activeClipId || state?.is_processing)
                              ? '1 AT A TIME'
                              : 'PROCESS CLIP'}
                          </button>
                        </div>

                        {/* Chat sample quotes from this exact peak moment */}
                        {p.samples && p.samples.length > 0 && (
                          <div className="bg-[#0d0f12] p-1.5 border border-[#262b34]/80 text-[10px] text-[#88909e] space-y-0.5">
                            {p.samples.slice(0, 2).map((s, si) => (
                              <div key={si} className="truncate">💬 {s}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </>
        )}

        {/* Terminal Logs */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center gap-1">
            <Terminal className="w-3 h-3" />
            PROCESS LOGS
          </div>
          <div className="h-24 overflow-y-auto text-[10px] font-mono space-y-0.5 bg-[#0d0f12] p-1.5 border border-[#262b34] text-[#88909e]">
            {logs.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap">{l}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}