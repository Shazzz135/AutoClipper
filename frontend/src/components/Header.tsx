import React, { useState, useEffect } from 'react';
import { Activity, Radio, Cpu, HardDrive, Sparkles, Video, Play, Edit2, Check, Volume2, VolumeX, Zap, UploadCloud, RefreshCw } from 'lucide-react';
import { sound } from '../services/sound';

export default function Header({ state, view, setView, onOpenPreview, isBuildingPreview, onTriggerTest }) {
  const isAllOk = state?.all_processes_ok;
  const activeClipId = state?.active_clip_id;
  const [isEditingChannel, setIsEditingChannel] = useState(false);
  const [channelInput, setChannelInput] = useState('');
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [togglingProcess, setTogglingProcess] = useState(false);
  const [togglingUpload, setTogglingUpload] = useState(false);
  const [togglingMonitoring, setTogglingMonitoring] = useState(false);
  const [ytAccounts, setYtAccounts] = useState([]);
  const [switchingYt, setSwitchingYt] = useState(false);
  const [isReauthing, setIsReauthing] = useState(false);

  const handleReauth = async () => {
    setIsReauthing(true);
    try {
      const res = await fetch('/api/youtube/reauth', { method: 'POST' });
      const data = await res.json();
      console.log('Reauth response:', data);
    } catch (e) {
      console.error('Reauth error:', e);
    } finally {
      setTimeout(() => setIsReauthing(false), 15000);
    }
  };

  const fetchYtAccounts = async () => {
    try {
      const res = await fetch('/api/youtube/accounts');
      if (res.ok) {
        const data = await res.json();
        setYtAccounts(data.accounts || []);
      }
    } catch (e) {
      console.error('Error fetching YouTube accounts:', e);
    }
  };

  useEffect(() => {
    fetchYtAccounts();
  }, [state?.youtube_channel]);

  const handleYtAccountSwitch = async (accountId) => {
    if (!accountId) return;
    setSwitchingYt(true);
    try {
      const res = await fetch('/api/youtube/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accountId })
      });
      if (res.ok) {
        await fetchYtAccounts();
        if (setView) setView('dashboard');
      }
    } catch (e) {
      console.error('Failed to switch YouTube account:', e);
    } finally {
      setSwitchingYt(false);
    }
  };

  const toggleMonitoring = async () => {
    setTogglingMonitoring(true);
    try {
      await fetch('/api/settings/toggle_monitoring', { method: 'POST' });
    } catch (err) {
      console.error('Failed to toggle monitoring:', err);
    } finally {
      setTogglingMonitoring(false);
    }
  };

  const toggleAutoProcess = async () => {
    setTogglingProcess(true);
    try {
      await fetch('/api/settings/auto_process', { method: 'POST' });
    } catch (err) {
      console.error('Failed to toggle auto process:', err);
    } finally {
      setTogglingProcess(false);
    }
  };

  const toggleAutoUpload = async () => {
    setTogglingUpload(true);
    try {
      await fetch('/api/settings/auto_upload', { method: 'POST' });
    } catch (err) {
      console.error('Failed to toggle auto upload:', err);
    } finally {
      setTogglingUpload(false);
    }
  };

  const toggleSound = () => {
    const nextVal = sound.toggle();
    setSoundEnabled(nextVal);
    if (nextVal) sound.playPing();
  };

  const handleChannelSwitch = async (e) => {
    e.preventDefault();
    if (!channelInput.trim()) return;
    try {
      await fetch('/api/channel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel: channelInput.trim() })
      });
      setIsEditingChannel(false);
      setChannelInput('');
      if (setView) setView('dashboard');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <header className="border-b border-[#262b34] bg-[#14171d] px-4 py-2 text-xs text-[#e1e4ea] space-y-2">
      {/* Top Row: Stream Info & Telemetry */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-1.5 border-b border-[#262b34]/50">
        {/* Title & Brand */}
        <div className="flex items-center space-x-3">
          <span className="font-bold tracking-wider text-[#ff1e1e] flex items-center gap-1.5">
            <Video className="w-4 h-4" />
            AUTOCLIPPER
          </span>
          <span className="text-[#88909e]">|</span>
          <div className="flex items-center gap-1.5 text-[#e1e4ea]">
            <Radio className={`w-3.5 h-3.5 ${state?.stream_online ? 'text-[#00e676]' : 'text-yellow-400'}`} />
            <span>STREAM:</span>

            {isEditingChannel ? (
              <form onSubmit={handleChannelSwitch} className="flex items-center gap-1">
                <input
                  type="text"
                  placeholder="streamer_name"
                  value={channelInput}
                  onChange={(e) => setChannelInput(e.target.value)}
                  className="bg-[#0d0f12] border border-[#ff1e1e] px-1.5 py-0.5 text-xs font-mono text-white outline-none w-28"
                  autoFocus
                />
                <button type="submit" className="bg-[#ff1e1e] text-white px-1 py-0.5 text-[10px] font-bold">
                  <Check className="w-3 h-3" />
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingChannel(false)}
                  className="bg-[#262b34] text-[#88909e] px-1 py-0.5 text-[10px]"
                >
                  ✕
                </button>
              </form>
            ) : (
              <div className="flex items-center gap-1">
                <span className="font-semibold text-white">{state?.channel || 'jynxzi'}</span>
                <button
                  onClick={() => { setIsEditingChannel(true); setChannelInput(state?.channel || 'jynxzi'); }}
                  className="text-[#88909e] hover:text-white p-0.5 ml-0.5"
                  title="Switch to any other live Twitch streamer"
                >
                  <Edit2 className="w-3 h-3" />
                </button>
              </div>
            )}

            <span className={`px-1 py-0.5 text-[10px] uppercase font-bold rounded ${
              state?.is_monitoring === false
                ? 'bg-yellow-500/20 text-yellow-400'
                : state?.stream_online
                  ? 'bg-[#00e676]/20 text-[#00e676]'
                  : 'bg-yellow-500/20 text-yellow-400'
            }`}>
              {state?.is_monitoring === false ? 'PAUSED (OFF)' : state?.stream_online ? '720p60 LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>

        {/* System & Resource Telemetry */}
        <div className="flex items-center space-x-4 text-[#88909e]">
          <div className="flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5 text-blue-400" />
            <span>CPU:</span>
            <span className="text-white font-mono">{state?.cpu_usage_pct || 18}%</span>
          </div>

          <div className="flex items-center gap-1">
            <HardDrive className="w-3.5 h-3.5 text-purple-400" />
            <span>BUFFER:</span>
            <span className="text-white font-mono">{state?.buffer_size_mb || 0} MB</span>
          </div>

          <div className="flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
            <span>AI CALLS:</span>
            <span className="text-white font-mono">{state?.ai_calls_today || 0} / 30</span>
          </div>

          <div className="flex items-center gap-1">
            <span>CLIPS:</span>
            <span className="text-white font-mono">{state?.clips_count || 0}</span>
          </div>

          <div className="flex items-center gap-1.5 bg-[#0d0f12] px-2 py-0.5 border border-[#262b34] text-[11px] font-mono">
            <span className="text-[#88909e]">YT:</span>
            {state?.youtube_reauth_in_progress || isReauthing ? (
              <span className="text-yellow-400 font-bold animate-pulse flex items-center gap-1">
                <RefreshCw className="w-3 h-3 animate-spin" />
                WAITING FOR BROWSER APPROVAL...
              </span>
            ) : state?.youtube_auth_status === 'EXPIRED' ? (
              <div className="flex items-center gap-1.5">
                <span className="text-red-400 font-bold flex items-center gap-1" title={state?.youtube_auth_error || 'OAuth session expired'}>
                  ⚠️ SESSION EXPIRED
                </span>
                <button
                  type="button"
                  onClick={handleReauth}
                  className="bg-red-600 hover:bg-red-500 text-white font-bold px-1.5 py-0.5 text-[10px] rounded cursor-pointer transition-none"
                  title="Click to open browser and re-authorize YouTube account"
                >
                  RECONNECT
                </button>
              </div>
            ) : state?.youtube_auth_status === 'EXPIRING_SOON' ? (
              <div className="flex items-center gap-1.5">
                <span className="text-yellow-400 font-bold" title="Google 7-day testing token is approaching expiration">
                  ⚡ RENEW (~{Math.round(state?.youtube_token_days_old || 6)}d old)
                </span>
                <button
                  type="button"
                  onClick={handleReauth}
                  className="bg-yellow-600 hover:bg-yellow-500 text-black font-bold px-1.5 py-0.5 text-[10px] rounded cursor-pointer transition-none"
                  title="Click to renew YouTube authorization"
                >
                  RE-AUTH
                </button>
              </div>
            ) : ytAccounts.length > 0 ? (
              <select
                value={
                  ytAccounts.find(a => a.is_active || a.id.toLowerCase() === (state?.youtube_channel || '').toLowerCase())?.id ||
                  ytAccounts[0]?.id ||
                  ''
                }
                onChange={(e) => handleYtAccountSwitch(e.target.value)}
                disabled={switchingYt}
                className="bg-transparent text-[#00e676] font-bold outline-none cursor-pointer border-none py-0 text-[11px]"
                title="Select YouTube account to post to (automatically sets tracked Twitch streamer)"
              >
                {ytAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id} className="bg-[#14171d] text-white">
                    {acc.name} (#{acc.streamer})
                  </option>
                ))}
              </select>
            ) : (
              <span className={`font-bold ${state?.youtube_authenticated !== false && state?.youtube_channel !== 'NOT CONNECTED' ? 'text-[#00e676]' : 'text-yellow-400'}`}>
                {state?.youtube_authenticated !== false && state?.youtube_channel !== 'NOT CONNECTED' ? (state?.youtube_channel || 'CONNECTED') : 'NOT CONNECTED'}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Row: Automation Toggles & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Automation Toggles */}
        <div className="flex items-center space-x-2">
          {/* Master Running / Paused Button */}
          <button
            onClick={toggleMonitoring}
            disabled={togglingMonitoring}
            className={`border px-2.5 py-1 text-xs font-mono font-bold flex items-center gap-1.5 transition-none cursor-pointer ${
              state?.is_monitoring !== false
                ? 'border-[#00e676]/60 bg-[#00e676]/15 text-[#00e676] hover:bg-[#00e676]/25'
                : 'border-yellow-500/60 bg-yellow-500/15 text-yellow-400 hover:bg-yellow-500/25'
            }`}
            title={state?.is_monitoring !== false ? 'Click to PAUSE tracking streamer & chat' : 'Click to RESUME tracking streamer & chat'}
          >
            <span className={`w-2 h-2 rounded-full ${state?.is_monitoring !== false ? 'bg-[#00e676] animate-pulse' : 'bg-yellow-400'}`} />
            <span>{state?.is_monitoring !== false ? 'ENGINE: RUNNING' : 'ENGINE: PAUSED (OFF)'}</span>
          </button>

          {/* Togglable Auto-Process Button */}
          <button
            onClick={toggleAutoProcess}
            disabled={togglingProcess}
            className={`border px-2.5 py-1 text-xs font-mono font-semibold flex items-center gap-1.5 transition-none cursor-pointer ${
              state?.auto_process
                ? 'border-[#00e676]/60 bg-[#00e676]/15 text-[#00e676] hover:bg-[#00e676]/25'
                : 'border-[#262b34] bg-[#1a1f27] text-[#88909e] hover:text-white hover:bg-[#262b34]'
            }`}
            title={state?.auto_process ? 'Auto-Process is ON: Detected peaks will be automatically cut & rendered' : 'Auto-Process is OFF: Peaks wait in queue for manual processing'}
          >
            <Zap className={`w-3 h-3 ${state?.auto_process ? 'text-[#00e676] fill-[#00e676]' : 'text-[#88909e]'}`} />
            <span>AUTO-PROCESS:</span>
            <span className={`px-1 py-0.2 rounded text-[10px] font-bold ${state?.auto_process ? 'bg-[#00e676] text-black' : 'bg-[#262b34] text-[#88909e]'}`}>
              {state?.auto_process ? 'ON' : 'OFF'}
            </span>
          </button>

          {/* Togglable Auto-Upload Button */}
          <button
            onClick={toggleAutoUpload}
            disabled={togglingUpload}
            className={`border px-2.5 py-1 text-xs font-mono font-semibold flex items-center gap-1.5 transition-none cursor-pointer ${
              state?.auto_upload
                ? 'border-[#ff1e1e]/60 bg-[#ff1e1e]/15 text-[#ff1e1e] hover:bg-[#ff1e1e]/25'
                : 'border-[#262b34] bg-[#1a1f27] text-[#88909e] hover:text-white hover:bg-[#262b34]'
            }`}
            title={state?.auto_upload ? 'Auto-Upload is ON: Clips will be automatically scheduled to YouTube upon render' : 'Auto-Upload is OFF: Safe Confirmation Mode - you manually review and confirm before publishing'}
          >
            <UploadCloud className={`w-3.5 h-3.5 ${state?.auto_upload ? 'text-[#ff1e1e]' : 'text-[#88909e]'}`} />
            <span>AUTO-UPLOAD:</span>
            <span className={`px-1 py-0.2 rounded text-[10px] font-bold ${state?.auto_upload ? 'bg-[#ff1e1e] text-white' : 'bg-[#262b34] text-[#88909e]'}`}>
              {state?.auto_upload ? 'ON' : 'OFF'}
            </span>
          </button>

          {/* Sound Toggle */}
          <button
            onClick={toggleSound}
            className={`border border-[#262b34] p-1 text-xs font-mono flex items-center transition-none ${
              soundEnabled ? 'text-[#00e676] bg-[#1a1f27]' : 'text-[#88909e] bg-[#14171d]'
            }`}
            title={soundEnabled ? 'Peak Ping Sound: ON' : 'Peak Ping Sound: MUTED'}
          >
            {soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Right-aligned Navigation & Trigger Group */}
        <div className="flex items-center space-x-2 ml-auto">
          <span className="text-[#262b34]">|</span>

          <button
            onClick={onTriggerTest}
            className="border border-[#262b34] bg-[#1a1f27] hover:bg-[#262b34] px-2.5 py-1 text-white font-mono text-xs flex items-center gap-1 transition-none"
            title="Simulate a chat velocity peak to test the pipeline"
          >
            <Play className="w-3 h-3 text-[#ff1e1e]" />
            TEST PEAK TRIGGER
          </button>

          {view === 'dashboard' ? (
            <button
              onClick={() => (onOpenPreview ? onOpenPreview() : setView('preview'))}
              disabled={!activeClipId || !state?.active_clip?.clip_created || isBuildingPreview}
              className={`px-3 py-1 text-xs font-mono font-bold transition-none ${
                activeClipId && state?.active_clip?.clip_created
                  ? 'bg-[#ff1e1e] text-white hover:bg-[#d01818] cursor-pointer'
                  : 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
              }`}
              title={state?.active_clip?.clip_created ? 'Open Preview & Post Page' : 'Click Confirm & Create Clip in the 16:9 Studio first'}
            >
              PREVIEW CLIP {state?.active_clip?.clip_created ? `(${state.active_clip.date_short || state.active_clip.name})` : ''} &rarr;
            </button>
          ) : (
            <button
              onClick={() => setView('dashboard')}
              className="bg-[#262b34] text-white hover:bg-[#343b47] px-3 py-1 text-xs font-mono transition-none cursor-pointer"
            >
              &larr; BACK TO 16:9 STUDIO
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
