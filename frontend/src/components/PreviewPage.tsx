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
  ArrowLeft
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
  const [isDirty, setIsDirty] = useState(false);
  const isDirtyRef = useRef(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);

  const [ytAccounts, setYtAccounts] = useState([]);
  const [isSwitchingAccount, setIsSwitchingAccount] = useState(false);

  const videoRef = useRef(null);

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
          setActionStatus(`✓ Published to YouTube: ${data.youtube_url || ''} (Storage reclaimed)`);
          if (onDiscard) onDiscard();
        }
        if (!isDirtyRef.current) {
          setTitle(data.title || '');
          setDescription(data.description || '');
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
        body: JSON.stringify({ title: title.trim(), description: description.trim() })
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
    setActionStatus('✓ Approved clip for scheduled YouTube upload. Storage reclaimed once posted.');
    await fetch(`/api/clips/${clipId}/approve`, { method: 'POST' });
    setClip((prev) => prev ? { ...prev, status: 'APPROVED' } : prev);
    if (onDiscard) onDiscard();
  };

  const handleUploadNow = async () => {
    if (isDirtyRef.current) {
      await handleSaveMetadata();
    }
    setActionStatus('Uploading directly to YouTube Shorts. Storage reclaimed once posted...');
    await fetch(`/api/clips/${clipId}/upload_now`, { method: 'POST' });
    setClip((prev) => prev ? { ...prev, status: 'UPLOADING' } : prev);
    if (onDiscard) onDiscard();
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
            clip.status === 'REJECTED' || clip.status === 'DISCARDED' ? 'bg-red-500/20 text-red-400' :
            'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/40'
          }`}>
            {clip.status}
          </span>
        </div>
      </div>

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
          <div className="space-y-3">
            <div className="text-xs font-bold text-white uppercase flex items-center justify-between border-b border-[#262b34] pb-2">
              <span>PUBLISHING DESTINATION</span>
              {ytAccounts.length > 0 ? (
                <div className="flex items-center gap-1.5 text-[10px] bg-[#0d0f12] px-2 py-0.5 border border-[#ff1e1e]/40">
                  <select
                    value={
                      ytAccounts.find(a => a.is_active || a.id.toLowerCase() === (state?.youtube_channel || channelInfo?.channel_title || '').toLowerCase() || a.name.toLowerCase() === (channelInfo?.channel_title || state?.youtube_channel || '').toLowerCase())?.id ||
                      ytAccounts[0]?.id || ''
                    }
                    onChange={(e) => handleAccountSwitch(e.target.value)}
                    disabled={isSwitchingAccount}
                    className="bg-transparent text-[#ff1e1e] font-bold outline-none cursor-pointer border-none py-0 text-[10px]"
                  >
                    {ytAccounts.map((acc) => (
                      <option key={acc.id} value={acc.id} className="bg-[#14171d] text-white">
                        {acc.name} (#{acc.streamer})
                      </option>
                    ))}
                  </select>
                </div>
              ) : channelInfo?.channel_title ? (
                <span className="text-white text-[10px] bg-[#0d0f12] px-2 py-0.5 border border-[#ff1e1e]/40">
                  Target: <strong className="text-[#ff1e1e]">{channelInfo.channel_title}</strong>
                </span>
              ) : null}
            </div>

            <div className="p-2.5 bg-[#0d0f12] border border-[#262b34] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 text-white">
                  <Calendar className="w-3.5 h-3.5 text-yellow-400" />
                  <span>Assigned Slot: <strong className="text-[#00e676]">{clip.scheduled_slot_display}</strong></span>
                </div>
                <span className="text-[10px] text-[#88909e]">EST</span>
              </div>
            </div>

            {clip.youtube_url && (
              <div className="p-2.5 bg-[#00e676]/10 border border-[#00e676]/30 text-xs text-[#00e676] flex items-center justify-between">
                <span>Published: {clip.youtube_url}</span>
                <a href={clip.youtube_url} target="_blank" rel="noreferrer" className="underline flex items-center gap-1">
                  Open Short <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}

            {actionStatus && (
              <div className="text-xs text-yellow-400 bg-yellow-500/10 p-2.5 border border-yellow-500/20">
                {actionStatus}
              </div>
            )}
          </div>

          {/* Action Buttons */}
          {clip.status === 'PENDING_REVIEW' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-[#262b34]">
              <button
                onClick={handleApprove}
                className="bg-[#00e676] hover:bg-[#00c853] text-black font-bold text-xs py-2.5 flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                title="Approve for scheduled release. Purged from SSD after upload."
              >
                <Check className="w-4 h-4" />
                APPROVE
              </button>

              <button
                onClick={handleUploadNow}
                className="bg-[#ff1e1e] hover:bg-[#d01818] text-white font-bold text-xs py-2.5 flex items-center justify-center gap-1.5 transition-none cursor-pointer"
                title="Publish directly to YouTube Shorts now. Purged from SSD after upload."
              >
                <Upload className="w-4 h-4" />
                UPLOAD NOW
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
