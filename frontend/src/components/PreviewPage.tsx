import React, { useState, useEffect, useRef } from 'react';
import {
  Download,
  Upload,
  Trash2,
  Clock,
  Check,
  ExternalLink,
  Calendar,
  Save,
  RotateCcw,
  Edit3,
  Sparkles,
  Film,
  ArrowLeft,
  MessageSquare,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Terminal,
  UploadCloud
} from 'lucide-react';

export default function PreviewPage({ clipId, onBack, onDiscard, state }) {
  const [clip, setClip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionStatus, setActionStatus] = useState(null);
  const [timeLeft, setTimeLeft] = useState(null);
  const [schedulePreview, setSchedulePreview] = useState(null);
  const [channelInfo, setChannelInfo] = useState(null);

  // Editable metadata state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [firstComment, setFirstComment] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const isDirtyRef = useRef(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);

  const [ytAccounts, setYtAccounts] = useState([]);
  const [isSwitchingAccount, setIsSwitchingAccount] = useState(false);

  const videoRef = useRef(null);
  const apiLogsContainerRef = useRef(null);

  const rawLogs = state?.col3?.logs || [];
  const apiLogs = rawLogs.filter((l) =>
    l.includes('YouTube') ||
    l.includes('upload') ||
    l.includes('Upload') ||
    l.includes('Category') ||
    l.includes('Audience') ||
    l.includes('License') ||
    l.includes('Tags') ||
    l.includes('thumbnail') ||
    l.includes('comment') ||
    l.includes('Approval') ||
    l.includes('SUCCESS') ||
    l.includes('failed') ||
    l.includes('Shorts') ||
    l.includes('Video ID')
  );
  const displayLogs = apiLogs.length > 0 ? apiLogs : rawLogs;

  useEffect(() => {
    if (apiLogsContainerRef.current) {
      apiLogsContainerRef.current.scrollTop = apiLogsContainerRef.current.scrollHeight;
    }
  }, [rawLogs.length]);

  useEffect(() => {
    fetchClipDetails();
    fetchSchedulePreview();
    fetchChannelInfo();
    fetchYtAccounts();
    const interval = setInterval(fetchClipDetails, 2000);
    return () => clearInterval(interval);
  }, [clipId]);

  const fetchYtAccounts = async () => {
    try {
      const res = await fetch('/api/youtube/accounts');
      if (res.ok) {
        const data = await res.json();
        setYtAccounts(data.accounts || []);
      }
    } catch (e) {
      console.error('Error fetching accounts:', e);
    }
  };

  const handleAccountSwitch = async (accountId) => {
    if (!accountId) return;
    setIsSwitchingAccount(true);
    try {
      const res = await fetch('/api/youtube/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accountId })
      });
      if (res.ok) {
        await fetchChannelInfo();
        await fetchYtAccounts();
        await fetchSchedulePreview();
      }
    } catch (e) {
      console.error('Failed to switch YouTube account:', e);
    } finally {
      setIsSwitchingAccount(false);
    }
  };

  const fetchChannelInfo = async () => {
    try {
      const res = await fetch('/api/youtube/channel');
      if (res.ok) {
        const data = await res.json();
        setChannelInfo(data);
      }
    } catch (e) {
      console.error('Error fetching channel info:', e);
    }
  };

  const fetchSchedulePreview = async () => {
    try {
      const res = await fetch('/api/schedule/preview');
      if (res.ok) {
        const data = await res.json();
        setSchedulePreview(data);
      }
    } catch (e) {
      console.error('Error fetching schedule preview:', e);
    }
  };

  useEffect(() => {
    if (!clip?.review_expires_at) return;
    const updateCountdown = () => {
      const now = Date.now() / 1000;
      const remaining = Math.max(0, Math.floor(clip.review_expires_at - now));
      const mins = Math.floor(remaining / 60);
      const secs = remaining % 60;
      setTimeLeft(`${mins}:${secs < 10 ? '0' : ''}${secs}`);
    };
    updateCountdown();
    const timer = setInterval(updateCountdown, 1000);
    return () => clearInterval(timer);
  }, [clip]);

  const fetchClipDetails = async () => {
    if (!clipId) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/clips/${clipId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'DISCARDED' || data.status === 'REJECTED') {
          setClip((prev) => prev ? { ...prev, status: 'DISCARDED' } : data);
          if (onDiscard) onDiscard();
          return;
        }
        setClip(data);
        if (data.status === 'UPLOADED') {
          setActionStatus(`✓ Published to YouTube Shorts: ${data.youtube_url || ''}`);
        }
        if (!isDirtyRef.current) {
          setTitle(data.title || '');
          setDescription(data.description || '');
          setFirstComment(data.first_comment || '');
        }
      } else {
        if (onDiscard) onDiscard();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveMetadata = async () => {
    setIsSaving(true);
    setSaveStatus('Saving metadata...');
    try {
      const res = await fetch(`/api/clips/${clipId}/metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          first_comment: firstComment.trim()
        })
      });
      if (res.ok) {
        setIsDirty(false);
        isDirtyRef.current = false;
        setSaveStatus('Metadata saved successfully!');
        setTimeout(() => setSaveStatus(null), 3000);
        fetchClipDetails();
        return true;
      } else {
        setSaveStatus('Failed to save metadata');
        return false;
      }
    } catch (err) {
      setSaveStatus('Error saving metadata');
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetMetadata = () => {
    if (clip) {
      setTitle(clip.title || '');
      setDescription(clip.description || '');
      setFirstComment(clip.first_comment || '');
      setIsDirty(false);
      isDirtyRef.current = false;
      setSaveStatus(null);
    }
  };

  const handleGenerateAi = async () => {
    setIsAiGenerating(true);
    setSaveStatus('AI generating viral title & tags...');
    try {
      const res = await fetch(`/api/clips/${clipId}/generate_ai`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.metadata) {
          setTitle(data.metadata.title);
          setDescription(data.metadata.description);
          if (data.metadata.first_comment) {
            setFirstComment(data.metadata.first_comment);
          }
          setIsDirty(false);
          isDirtyRef.current = false;
          setSaveStatus('✨ AI details generated successfully!');
          setTimeout(() => setSaveStatus(null), 3500);
          fetchClipDetails();
        }
      } else {
        setSaveStatus('Failed to generate AI metadata');
      }
    } catch (err) {
      console.error(err);
      setSaveStatus('AI generation error');
    } finally {
      setIsAiGenerating(false);
    }
  };

  const handleApprove = async () => {
    if (isDirtyRef.current) {
      await handleSaveMetadata();
    }
    setActionStatus('✓ Approved clip for scheduled release. Initiating YouTube Shorts upload & verification...');
    await fetch(`/api/clips/${clipId}/approve`, { method: 'POST' });
    setClip((prev) => prev ? { ...prev, status: 'APPROVED' } : prev);
  };

  const handleUploadNow = async () => {
    if (isDirtyRef.current) {
      await handleSaveMetadata();
    }
    setActionStatus('Uploading directly to YouTube Shorts. Transcode & verification in progress...');
    await fetch(`/api/clips/${clipId}/upload_now`, { method: 'POST' });
    setClip((prev) => prev ? { ...prev, status: 'UPLOADING' } : prev);
  };

  const handleReject = async () => {
    if (window.confirm('Reject and permanently purge this clip from SSD storage?')) {
      setActionStatus('✓ Clip rejected and all video files purged from SSD.');
      if (videoRef.current) {
        try {
          videoRef.current.pause();
          videoRef.current.removeAttribute('src');
          videoRef.current.load();
        } catch (e) {}
      }
      try {
        await fetch(`/api/clips/${clipId}/reject`, { method: 'POST' });
      } catch (err) {
        console.error('Failed to call reject endpoint:', err);
      }
      setClip((prev) => prev ? { ...prev, status: 'REJECTED' } : prev);
      if (onDiscard) onDiscard();
    }
  };

  if (loading && !clip) {
    return (
      <div className="p-8 text-center text-xs font-mono text-[#88909e]">
        LOADING CLIP DATA...
      </div>
    );
  }

  if (!clip) {
    return (
      <div className="p-8 text-center text-xs font-mono text-red-400">
        CLIP NOT FOUND OR ALREADY PURGED.
        <div className="mt-4">
          <button onClick={onBack} className="bg-[#262b34] px-4 py-2 text-white font-mono text-xs cursor-pointer">
            &larr; BACK TO STUDIO
          </button>
        </div>
      </div>
    );
  }

  const verticalShortUrl = `/media/${clip.video_file}?v=${clip.version || 1}`;

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4 font-mono select-none">
      {/* Top Bar Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#262b34] pb-3">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-xs bg-[#14171d] hover:bg-[#262b34] border border-[#262b34] px-3 py-1.5 text-[#88909e] hover:text-white flex items-center gap-1.5 transition-none cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            BACK TO 16:9 STUDIO
          </button>
          <div>
            <h1 className="text-xs md:text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <span className="text-[#88909e]">CLIP:</span>
              <span className="text-[#00e676]">{clip.name || clip.date || clip.created_at}</span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {timeLeft && (
            <span className="text-xs bg-[#14171d] border border-[#262b34] px-2.5 py-1 text-yellow-400 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              AUTO-DECIDE IN {timeLeft}
            </span>
          )}
          <span className={`px-2.5 py-1 text-xs font-bold uppercase rounded ${
            clip.status === 'UPLOADED' ? 'bg-[#00e676]/20 text-[#00e676]' :
            clip.status === 'UPLOADING' ? 'bg-yellow-500/20 text-yellow-400' :
            clip.status === 'UPLOAD_ERROR' ? 'bg-red-500/20 text-red-400 border border-red-500/40' :
            clip.status === 'REJECTED' || clip.status === 'DISCARDED' ? 'bg-red-500/20 text-red-400' :
            'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/40'
          }`}>
            {clip.status}
          </span>
        </div>
      </div>

      {/* Prominent Upload Status Banners */}
      {clip.status === 'UPLOADED' && (
        <div className="p-4 bg-[#00e676]/10 border border-[#00e676]/50 rounded text-xs text-[#00e676] flex flex-col sm:flex-row items-center justify-between gap-3 shadow-lg">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-[#00e676] shrink-0" />
            <div>
              <div className="font-bold text-sm text-white flex items-center gap-2">
                <span>SUCCESS! CLIP UPLOADED TO YOUTUBE SHORTS</span>
                <span className="bg-[#00e676]/20 text-[#00e676] px-1.5 py-0.5 rounded text-[10px] font-mono">LIVE / INGESTED</span>
              </div>
              <div className="text-xs text-[#88909e] mt-0.5">
                Google received the 60fps vertical file. Storage will be reclaimed once reviewed.
              </div>
            </div>
          </div>
          {clip.youtube_url && (
            <a
              href={clip.youtube_url}
              target="_blank"
              rel="noreferrer"
              className="bg-[#00e676] hover:bg-[#00c853] text-black font-bold px-4 py-2 text-xs flex items-center gap-2 cursor-pointer shrink-0"
            >
              <ExternalLink className="w-4 h-4" />
              WATCH ON YOUTUBE SHORTS
            </a>
          )}
        </div>
      )}

      {clip.status === 'UPLOADING' && (
        <div className="p-4 bg-yellow-500/10 border border-yellow-500/40 rounded text-xs text-yellow-300 flex items-center justify-between gap-3 shadow-lg">
          <div className="flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-yellow-400 animate-spin shrink-0" />
            <div>
              <div className="font-bold text-sm text-white">UPLOADING DIRECTLY TO YOUTUBE SHORTS...</div>
              <div className="text-xs text-yellow-300/80 mt-0.5">
                Transferring 60fps vertical stream to Google servers with automatic resume. A success confirmation will appear here once complete.
              </div>
            </div>
          </div>
        </div>
      )}

      {clip.status === 'UPLOAD_ERROR' && (
        <div className="p-4 bg-red-950/40 border border-red-500/60 rounded text-xs text-red-200 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-lg">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-red-400 shrink-0" />
            <div>
              <div className="font-bold text-sm text-red-300">
                {clip.upload_error?.includes('limit') ? 'YOUTUBE DAILY UPLOAD LIMIT REACHED' : 'YOUTUBE UPLOAD FAILED'}
              </div>
              <div className="text-xs text-red-300 mt-1 max-w-2xl leading-relaxed">
                {clip.upload_error || 'Network connection dropped while communicating with Google API.'}
              </div>
              {clip.upload_error?.includes('limit') && (
                <div className="text-[11px] text-yellow-300/90 mt-1 flex items-center gap-1.5">
                  <span>💡 Tip: Enable <strong>Advanced Features</strong> in YouTube Studio to unlock up to 100 uploads/day, or switch to your other YouTube account in the navbar.</span>
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {clip.upload_error?.includes('limit') && (
              <a
                href="https://studio.youtube.com"
                target="_blank"
                rel="noreferrer"
                className="bg-yellow-500 hover:bg-yellow-400 text-black font-bold px-3 py-1.5 text-xs flex items-center gap-1.5 cursor-pointer"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                YOUTUBE STUDIO
              </a>
            )}
            <button
              onClick={handleUploadNow}
              className="bg-[#ff1e1e] hover:bg-[#d01818] text-white font-bold px-3 py-1.5 text-xs flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              RETRY UPLOAD NOW
            </button>
            <button
              onClick={handleApprove}
              className="bg-[#00e676] hover:bg-[#00c853] text-black font-bold px-3 py-1.5 text-xs flex items-center gap-1.5 cursor-pointer"
            >
              <Check className="w-3.5 h-3.5" />
              SCHEDULE INSTEAD
            </button>
          </div>
        </div>
      )}

      {/* Main 9:16 Vertical Preview & Download Card */}
      <div className="border border-[#262b34] bg-[#14171d] p-4 space-y-4">
        <div className="flex items-center justify-between border-b border-[#262b34] pb-2">
          <div className="flex items-center gap-2 text-white font-bold text-xs uppercase">
            <Film className="w-4 h-4 text-[#ff1e1e]" />
            <span>9:16 VERTICAL SHORT PREVIEW ({clip.duration_sec}s)</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-[#88909e]">
              Cut Range: <strong className="text-white">{clip.trim_start}s &rarr; {clip.trim_end}s</strong>
            </span>
            <a
              href={verticalShortUrl}
              download={`Short_${(clip.name || clip.date || 'Clip').replace(/[^a-zA-Z0-9_-]/g, '_')}.mp4`}
              className="bg-[#00e676] hover:bg-[#00c853] px-3 py-1.5 text-xs font-bold text-black flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              DOWNLOAD MP4 ({clip.size_mb} MB)
            </a>
          </div>
        </div>

        {/* 9:16 Vertical Player Container */}
        <div className="flex justify-center py-2">
          <div className="w-[280px] h-[498px] bg-black border-2 border-[#262b34] shadow-2xl relative overflow-hidden flex items-center justify-center">
            {clip.status === 'REJECTED' || clip.status === 'DISCARDED' ? (
              <div className="text-xs text-red-400 text-center p-4">
                CLIP PURGED FROM SSD
              </div>
            ) : (
              <video
                ref={videoRef}
                key={verticalShortUrl}
                src={verticalShortUrl}
                controls
                playsInline
                className="w-full h-full object-cover"
              />
            )}
          </div>
        </div>
      </div>

      {/* Video Metadata & YouTube Publishing Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Metadata Card (7 cols) */}
        <div className="lg:col-span-7 border border-[#262b34] bg-[#14171d] p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-[#262b34] pb-2">
            <div className="text-xs font-bold text-white uppercase flex items-center gap-1.5">
              <Edit3 className="w-3.5 h-3.5 text-[#ff1e1e]" />
              <span>YOUTUBE METADATA & TITLE</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleGenerateAi}
                disabled={isAiGenerating}
                className="bg-purple-600 hover:bg-purple-500 disabled:bg-[#262b34] text-white px-2.5 py-1 text-[10px] font-bold flex items-center gap-1 transition-none cursor-pointer"
              >
                <Sparkles className="w-3 h-3 text-yellow-300" />
                {isAiGenerating ? 'AI GENERATING...' : 'GENERATE WITH AI'}
              </button>
              {isDirty && (
                <span className="text-[10px] text-yellow-400 bg-yellow-400/10 px-2 py-0.5 border border-yellow-400/30">
                  UNSAVED
                </span>
              )}
              {saveStatus && (
                <span className="text-[10px] text-[#00e676] bg-[#00e676]/10 px-2 py-0.5 border border-[#00e676]/30">
                  {saveStatus}
                </span>
              )}
            </div>
          </div>

          {/* Title Input */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-[#88909e] uppercase font-bold">
                YouTube Short Title
              </label>
              <span className={`text-[10px] ${title.length > 100 ? 'text-red-400 font-bold' : 'text-[#88909e]'}`}>
                {title.length}/100 chars
              </span>
            </div>
            <input
              type="text"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setIsDirty(true);
                isDirtyRef.current = true;
              }}
              maxLength={120}
              placeholder="Enter Short title with emojis/hashtags..."
              className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#00e676] text-xs font-bold text-white outline-none"
            />
          </div>

          {/* Description Textarea */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-[#88909e] uppercase font-bold">
                Description & Tags
              </label>
              <span className="text-[10px] text-[#88909e]">
                {description.length}/5000 chars
              </span>
            </div>
            <textarea
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setIsDirty(true);
                isDirtyRef.current = true;
              }}
              rows={3}
              placeholder="Video description, channel credits, #shorts hashtags..."
              className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#00e676] text-xs text-[#e1e4ea] outline-none resize-y"
            />
          </div>

          {/* First / Discussion Comment Textarea */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-[#88909e] uppercase font-bold flex items-center gap-1">
                <MessageSquare className="w-3 h-3 text-[#00e676]" />
                First Comment (Auto-Posted as Channel Author)
              </label>
              <span className="text-[10px] text-[#88909e]">
                {firstComment.length}/400 chars
              </span>
            </div>
            <textarea
              value={firstComment}
              onChange={(e) => {
                setFirstComment(e.target.value);
                setIsDirty(true);
                isDirtyRef.current = true;
              }}
              rows={2}
              placeholder="e.g. Drop your thoughts below: Was this a clutch or a choke?! 👇💀"
              className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#00e676] text-xs text-[#e1e4ea] outline-none resize-y"
            />
          </div>

          {/* Save / Reset */}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleSaveMetadata}
              disabled={isSaving || !isDirty}
              className={`px-3 py-1.5 text-xs font-bold flex items-center gap-1.5 transition-none ${
                isDirty
                  ? 'bg-[#00e676] hover:bg-[#00c853] text-black cursor-pointer'
                  : 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
              }`}
            >
              <Save className="w-3.5 h-3.5" />
              {isSaving ? 'SAVING...' : 'SAVE METADATA'}
            </button>

            {isDirty && (
              <button
                type="button"
                onClick={handleResetMetadata}
                className="bg-[#262b34] hover:bg-[#343b47] text-[#88909e] hover:text-white px-2.5 py-1.5 text-xs flex items-center gap-1 transition-none cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                REVERT
              </button>
            )}
          </div>
        </div>

        {/* YouTube Publishing & Action Buttons (5 cols) */}
        <div className="lg:col-span-5 border border-[#262b34] bg-[#14171d] p-4 space-y-3 flex flex-col justify-between">
          {/* Unified Publishing Channel & Allowance Card */}
          <div className="border border-[#262b34] bg-[#14171d] p-3.5 space-y-3 font-mono">
            <div className="flex items-center justify-between border-b border-[#262b34] pb-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-white uppercase tracking-wide">
                <UploadCloud className="w-3.5 h-3.5 text-[#ff1e1e]" />
                <span>PUBLISHING CHANNEL & ALLOWANCE</span>
              </div>
              {state?.youtube_quota?.reset_display && (
                <span className="text-[10px] text-[#88909e]">
                  Quota resets in <strong className="text-white">{state.youtube_quota.reset_display}</strong>
                </span>
              )}
            </div>

            {/* Channel Switcher Pills */}
            {ytAccounts.length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {ytAccounts.map((acc) => {
                  const accQuota = state?.youtube_quota?.accounts?.[acc.id];
                  const remaining = accQuota ? accQuota.remaining_today : 3;
                  const isCurrent = acc.is_active || (state?.youtube_channel && acc.id.toLowerCase() === state.youtube_channel.toLowerCase());

                  return (
                    <button
                      key={acc.id}
                      type="button"
                      disabled={isSwitchingAccount || isCurrent}
                      onClick={() => handleAccountSwitch(acc.id)}
                      className={`p-2.5 rounded text-left border flex flex-col justify-between transition-none cursor-pointer select-none ${
                        isCurrent
                          ? 'bg-[#1b251d] border-[#00e676]/60 text-white shadow-sm'
                          : 'bg-[#0d0f12] border-[#262b34] text-[#88909e] hover:border-[#434c5e] hover:text-white'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-bold">
                        <span className="truncate">{acc.name}</span>
                        {isCurrent && (
                          <span className="text-[#00e676] text-[9px] uppercase font-bold tracking-wider bg-[#00e676]/20 px-1 py-0.2 rounded">
                            ACTIVE
                          </span>
                        )}
                      </div>
                      <div className="mt-1.5 flex items-center justify-between text-[11px]">
                        <span className={`font-bold ${remaining > 0 ? 'text-[#00e676]' : 'text-red-400'}`}>
                          {remaining} of 3 slots left
                        </span>
                        <span className="text-[10px] text-[#555d6e]">
                          {3 - remaining} posted today
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Release Schedule Slot Bar */}
            <div className="p-2.5 bg-[#0d0f12] border border-[#262b34] rounded flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-yellow-400 shrink-0" />
                <span className="text-[#88909e]">
                  Scheduled Release: <strong className="text-[#00e676]">{clip.scheduled_slot_display}</strong>
                </span>
              </div>
              <span className="text-[10px] text-[#88909e] hidden sm:inline">
                Project Total: {state?.youtube_quota?.total_used_today ?? 0} of 6 used
              </span>
            </div>

            {/* Capacity Warning */}
            {state?.youtube_quota?.active_at_capacity && (
              <div className="p-2.5 bg-yellow-950/40 border border-yellow-500/50 rounded text-xs text-yellow-300">
                ⚠️ {state.youtube_quota.active_account} reached its 3-video limit for today. Switch channels above or schedule for tomorrow.
              </div>
            )}

            {clip.youtube_url && (
              <div className="p-2.5 bg-[#00e676]/10 border border-[#00e676]/30 text-xs text-[#00e676] flex items-center justify-between rounded">
                <span>Published: {clip.youtube_url}</span>
                <a href={clip.youtube_url} target="_blank" rel="noreferrer" className="underline flex items-center gap-1 font-bold">
                  Open Short <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}
          </div>

            {actionStatus && (
              <div className="text-xs text-yellow-400 bg-yellow-500/10 p-2.5 border border-yellow-500/20">
                {actionStatus}
              </div>
            )}

            {state?.youtube_reauth_in_progress && (
              <div className="p-2.5 bg-yellow-950/40 border border-yellow-500/60 text-xs text-yellow-200 flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 font-bold animate-pulse">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-yellow-400" />
                  Checking verification every 10s until reconnected...
                </span>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await fetch('/api/youtube/cancel_reauth', { method: 'POST' });
                    } catch (e) {}
                  }}
                  className="bg-[#262b34] hover:bg-[#343b47] text-[#88909e] hover:text-white px-2 py-0.5 text-[10px] rounded"
                >
                  Cancel
                </button>
              </div>
            )}

            {!state?.youtube_reauth_in_progress && state?.youtube_auth_status === 'EXPIRED' && (
              <div className="p-2.5 bg-red-950/40 border border-red-500/60 text-xs text-red-200 flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 font-bold">
                  ⚠️ Session expired for {state?.youtube_channel || 'account'} (switch accounts above or reconnect)
                </span>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await fetch('/api/youtube/reauth', { method: 'POST' });
                      setActionStatus('Opening browser to reconnect YouTube account (checking every 10s)...');
                    } catch (e) {
                      console.error(e);
                    }
                  }}
                  className="bg-red-600 hover:bg-red-500 text-white font-bold px-2 py-1 text-[11px] rounded cursor-pointer transition-none"
                >
                  RECONNECT NOW
                </button>
              </div>
            )}

          {/* Live YouTube Data API Console */}
          <div className="border border-[#262b34] bg-[#0c0e12] p-3 space-y-2 font-mono rounded">
            <div className="flex items-center justify-between border-b border-[#262b34] pb-1.5">
              <div className="flex items-center gap-2">
                <Terminal className="w-3.5 h-3.5 text-[#ff1e1e]" />
                <span className="text-[11px] font-bold text-white tracking-wide">
                  LIVE YOUTUBE DATA API CONSOLE
                </span>
                {clip.status === 'UPLOADING' && (
                  <span className="text-[10px] bg-yellow-500/20 text-yellow-300 px-1.5 py-0.2 rounded animate-pulse">
                    ACTIVE TRANSMISSION
                  </span>
                )}
                {clip.status === 'UPLOADED' && (
                  <span className="text-[10px] bg-[#00e676]/20 text-[#00e676] px-1.5 py-0.2 rounded font-bold">
                    API SUCCESS
                  </span>
                )}
                {clip.status === 'UPLOAD_ERROR' && (
                  <span className="text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.2 rounded font-bold">
                    API FAILED
                  </span>
                )}
              </div>
              <span className="text-[10px] text-[#88909e]">Google API v3 Telemetry</span>
            </div>

            {/* Log Terminal Screen */}
            <div
              ref={apiLogsContainerRef}
              className="h-36 overflow-y-auto bg-[#08090c] p-2.5 rounded border border-[#1b1f27] text-[11px] space-y-1 select-text scrollbar-thin"
            >
              {displayLogs.length === 0 ? (
                <div className="text-[#555d6e] italic py-2">
                  Click APPROVE or UPLOAD NOW below to dispatch this clip. Real-time API authentication, metadata injection, chunk progress, thumbnail sync, and Shorts publication will stream here.
                </div>
              ) : (
                displayLogs.map((log, idx) => {
                  const isSuccess = log.includes('SUCCESS') || log.includes('✅') || log.includes('🎉') || log.includes('Uploaded successfully');
                  const isError = log.includes('failed') || log.includes('error') || log.includes('Fatal') || log.includes('❌') || log.includes('⚠️');
                  const isProgress = log.includes('progress:') || log.includes('sent') || log.includes('MB');
                  const isMeta = log.includes('Category:') || log.includes('Audience:') || log.includes('License:') || log.includes('Tags:') || log.includes('Configuring');

                  return (
                    <div
                      key={idx}
                      className={`${
                        isSuccess
                          ? 'text-[#00e676] font-bold'
                          : isError
                          ? 'text-red-400 font-bold'
                          : isProgress
                          ? 'text-yellow-300'
                          : isMeta
                          ? 'text-cyan-300'
                          : 'text-[#a6b0c2]'
                      }`}
                    >
                      {log}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* In-Flight Upload Status */}
          {(clip.status === 'UPLOADING' || clip.status === 'APPROVED') && (
            <div className="p-3 bg-cyan-950/40 border border-cyan-500/50 rounded flex items-center justify-between gap-2 text-xs text-cyan-200">
              <span className="flex items-center gap-2 font-bold animate-pulse">
                <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
                {clip.status === 'UPLOADING' ? 'Uploading directly to YouTube Shorts & verifying transcode...' : 'Approved. Scheduling release & uploading...'}
              </span>
              <span className="text-[10px] text-cyan-400 font-mono">Telemetry streaming below ↓</span>
            </div>
          )}

          {/* Upload Complete Card with Direct Link */}
          {clip.status === 'UPLOADED' && (
            <div className="p-3.5 bg-[#00e676]/10 border border-[#00e676]/50 rounded flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 border-t border-[#262b34]">
              <div className="flex items-center gap-2.5 text-[#00e676]">
                <CheckCircle2 className="w-5 h-5 text-[#00e676] shrink-0" />
                <div>
                  <div className="font-bold text-xs uppercase tracking-wider">Published to YouTube Shorts</div>
                  <div className="text-[11px] text-[#88909e]">Verified 9:16 vertical Short • Transcode complete</div>
                </div>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto">
                {clip.youtube_url && (
                  <a
                    href={clip.youtube_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 sm:flex-initial bg-[#00e676] hover:bg-[#00c853] text-black font-bold text-xs px-4 py-2 rounded flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                  >
                    VIEW SHORT <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
                <button
                  onClick={onBack}
                  className="bg-[#262b34] hover:bg-[#323844] text-white text-xs px-3.5 py-2 rounded font-mono cursor-pointer"
                >
                  STUDIO
                </button>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          {(clip.status === 'PENDING_REVIEW' || clip.status === 'UPLOAD_ERROR') && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-[#262b34]">
              <button
                onClick={handleApprove}
                className="bg-[#00e676] hover:bg-[#00c853] text-black font-bold text-xs py-2.5 flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                title="Approve for scheduled release. Purged from SSD after upload."
              >
                <Check className="w-4 h-4" />
                {clip.status === 'UPLOAD_ERROR' ? 'SCHEDULE RELEASE' : 'APPROVE'}
              </button>

              <button
                onClick={handleUploadNow}
                className="bg-[#ff1e1e] hover:bg-[#d01818] text-white font-bold text-xs py-2.5 flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                title="Publish directly to YouTube Shorts now. Purged from SSD after upload."
              >
                {clip.status === 'UPLOAD_ERROR' ? <RefreshCw className="w-4 h-4" /> : <Upload className="w-4 h-4" />}
                {clip.status === 'UPLOAD_ERROR' ? 'RETRY UPLOAD NOW' : 'UPLOAD NOW'}
              </button>

              <button
                onClick={handleReject}
                className="bg-[#262b34] hover:bg-red-950/60 hover:text-red-400 text-[#88909e] text-xs py-2.5 flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                title="Reject and immediately purge all video files from SSD"
              >
                <Trash2 className="w-4 h-4" />
                PURGE
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
