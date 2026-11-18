import React, { useState, useEffect, useRef } from 'react';
import {
  Download,
  Upload,
  Trash2,
  Clock,
  Check,
  AlertTriangle,
  ExternalLink,
  Calendar,
  Save,
  RotateCcw,
  Edit3,
  Sparkles
} from 'lucide-react';

export default function PreviewPage({ clipId, onBack, state }) {
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

  useEffect(() => {
    fetchClipDetails();
    fetchSchedulePreview();
    fetchChannelInfo();
    fetchYtAccounts();
    const interval = setInterval(fetchClipDetails, 2000);
    return () => clearInterval(interval);
  }, [clipId]);

  const [ytAccounts, setYtAccounts] = useState([]);
  const [isSwitchingAccount, setIsSwitchingAccount] = useState(false);

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
    try {
      const res = await fetch(`/api/clips/${clipId}`);
      if (res.ok) {
        const data = await res.json();
        setClip(data);
        if (!isDirtyRef.current) {
          setTitle(data.title || '');
          setDescription(data.description || '');
        }
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
    setSaveStatus('AI generating viral title, description & tags...');
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
    setActionStatus('Approving for scheduled upload...');
    await fetch(`/api/clips/${clipId}/approve`, { method: 'POST' });
    fetchClipDetails();
  };

  const handleUploadNow = async () => {
    if (isDirtyRef.current) {
      await handleSaveMetadata();
    }
    setActionStatus('Uploading directly to YouTube Shorts...');
    await fetch(`/api/clips/${clipId}/upload_now`, { method: 'POST' });
    fetchClipDetails();
  };

  const handleReject = async () => {
    if (window.confirm('Reject and permanently purge this clip from SSD storage?')) {
      setActionStatus('Rejecting and purging files...');
      await fetch(`/api/clips/${clipId}/reject`, { method: 'POST' });
      onBack();
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
          <button onClick={onBack} className="bg-[#262b34] px-4 py-2 text-white font-mono text-xs">
            &larr; BACK TO PROCESSES
          </button>
        </div>
      </div>
    );
  }

  const videoUrl = `/media/${clip.video_file}`;
  const thumbUrl = clip.thumbnail_file ? `/media/${clip.thumbnail_file}` : null;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Top Bar Navigation */}
      <div className="flex items-center justify-between border-b border-[#262b34] pb-4">
        <div>
          <button
            onClick={onBack}
            className="text-xs font-mono text-[#88909e] hover:text-white mb-1"
          >
            &larr; BACK TO PROCESSES DASHBOARD
          </button>
          <h1 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
            <span>CLIP PREVIEW:</span>
            <span className="text-[#00e676]">{clip.name || clip.date || clip.created_at}</span>
          </h1>
        </div>

        <div className="flex items-center space-x-2">
          <span className={`px-2.5 py-1 text-xs font-mono font-bold uppercase rounded ${
            clip.status === 'UPLOADED' ? 'bg-[#00e676]/20 text-[#00e676]' :
            clip.status === 'UPLOADING' ? 'bg-yellow-500/20 text-yellow-400' :
            clip.status === 'REJECTED' ? 'bg-red-500/20 text-red-400' :
            'bg-[#ff1e1e]/20 text-[#ff1e1e] border border-[#ff1e1e]/40'
          }`}>
            STATUS: {clip.status}
          </span>
        </div>
      </div>

      {/* Main Review Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: 9:16 Vertical Video Player (Cols 5) */}
        <div className="lg:col-span-5 flex flex-col items-center">
          <div className="w-[300px] h-[533px] bg-black border-2 border-[#262b34] overflow-hidden relative shadow-2xl">
            <video
              src={videoUrl}
              controls
              playsInline
              className="w-full h-full object-cover"
            />
          </div>

          <div className="w-[300px] mt-3">
            <a
              href={videoUrl}
              download={`Short_${(clip.name || clip.date || 'Clip').replace(/[^a-zA-Z0-9_-]/g, '_')}.mp4`}
              className="w-full bg-[#14171d] hover:bg-[#262b34] border border-[#262b34] py-2 text-xs font-mono text-white flex items-center justify-center gap-2 transition-none"
            >
              <Download className="w-3.5 h-3.5" />
              DOWNLOAD 1080x1920 MP4 ({clip.size_mb} MB)
            </a>
          </div>
        </div>

        {/* Right: Metadata & YouTube Actions (Cols 7) */}
        <div className="lg:col-span-7 space-y-4">
          {/* Editable Metadata Card */}
          <div className="border border-[#262b34] bg-[#14171d] p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-[#262b34] pb-2">
              <div className="text-[11px] font-bold text-[#88909e] uppercase flex items-center gap-1.5">
                <Edit3 className="w-3.5 h-3.5 text-[#ff1e1e]" />
                <span>VIDEO METADATA (AI POWERED)</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleGenerateAi}
                  disabled={isAiGenerating}
                  className="bg-purple-600 hover:bg-purple-500 disabled:bg-[#262b34] text-white px-2 py-0.5 text-[10px] font-mono font-bold flex items-center gap-1 transition-none"
                  title="Generate viral title, description, and tags with AI"
                >
                  <Sparkles className="w-3 h-3 text-yellow-300" />
                  {isAiGenerating ? 'AI GENERATING...' : 'GENERATE WITH AI'}
                </button>
                {isDirty && (
                  <span className="text-[10px] font-mono text-yellow-400 bg-yellow-400/10 px-2 py-0.5 border border-yellow-400/30">
                    UNSAVED
                  </span>
                )}
                {saveStatus && (
                  <span className="text-[10px] font-mono text-[#00e676] bg-[#00e676]/10 px-2 py-0.5 border border-[#00e676]/30">
                    {saveStatus}
                  </span>
                )}
              </div>
            </div>

            {/* Title Input */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[10px] text-[#88909e] uppercase font-bold">
                  Title (YouTube Shorts)
                </label>
                <span className={`text-[10px] font-mono ${title.length > 100 ? 'text-red-400 font-bold' : 'text-[#88909e]'}`}>
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
                className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#ff1e1e] text-xs font-mono font-bold text-white outline-none"
              />
              {title.length > 100 && (
                <div className="text-[10px] text-red-400 mt-1 font-mono">
                  ⚠ YouTube Shorts titles are best under 100 characters to prevent truncation.
                </div>
              )}
            </div>

            {/* Description Textarea */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[10px] text-[#88909e] uppercase font-bold">
                  Description & Tags
                </label>
                <span className="text-[10px] font-mono text-[#88909e]">
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
                rows={5}
                placeholder="Video description, channel credits, #shorts hashtags..."
                className="w-full p-2 bg-[#0d0f12] border border-[#262b34] focus:border-[#ff1e1e] text-xs font-mono text-[#e1e4ea] outline-none resize-y"
              />
            </div>

            {/* Save / Reset Actions */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleSaveMetadata}
                disabled={isSaving || !isDirty}
                className={`px-3 py-1.5 text-xs font-mono font-bold flex items-center gap-1.5 transition-none ${
                  isDirty
                    ? 'bg-[#00e676] hover:bg-[#00c853] text-black cursor-pointer'
                    : 'bg-[#262b34] text-[#88909e] cursor-not-allowed'
                }`}
              >
                <Save className="w-3.5 h-3.5" />
                {isSaving ? 'SAVING...' : 'SAVE METADATA'}
              </button>

              <button
                type="button"
                onClick={handleGenerateAi}
                disabled={isAiGenerating}
                className="bg-[#1a1f27] hover:bg-purple-950/60 text-purple-300 border border-purple-500/40 px-3 py-1.5 text-xs font-mono font-bold flex items-center gap-1.5 transition-none"
              >
                <Sparkles className="w-3.5 h-3.5 text-yellow-300" />
                {isAiGenerating ? 'AI GENERATING...' : '✨ GENERATE WITH AI'}
              </button>

              {isDirty && (
                <button
                  type="button"
                  onClick={handleResetMetadata}
                  className="bg-[#262b34] hover:bg-[#343b47] text-[#88909e] hover:text-white px-2.5 py-1.5 text-xs font-mono flex items-center gap-1 transition-none"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  REVERT
                </button>
              )}
            </div>

            {/* Tags Display */}
            {clip.tags && clip.tags.length > 0 && (
              <div className="pt-2 border-t border-[#262b34]">
                <label className="text-[10px] text-[#88909e] uppercase block mb-1">Extracted Tags</label>
                <div className="flex flex-wrap gap-1 text-[10px] font-mono">
                  {clip.tags.map((tag, i) => (
                    <span key={i} className="bg-[#262b34] px-1.5 py-0.5 text-white">
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Thumbnail Display */}
            {thumbUrl && (
              <div className="pt-2 border-t border-[#262b34]">
                <label className="text-[10px] text-[#88909e] uppercase block mb-1">
                  Selected Thumbnail (Peak Expression Landmark)
                </label>
                <img
                  src={thumbUrl}
                  alt="Expression Thumbnail"
                  className="w-32 h-20 object-cover border border-[#262b34]"
                />
              </div>
            )}
          </div>

          {/* YouTube Delivery & Actions Card */}
          <div className="border border-[#262b34] bg-[#14171d] p-4 space-y-3">
            <div className="text-[11px] font-bold text-[#88909e] uppercase flex flex-wrap items-center justify-between gap-1.5 border-b border-[#262b34] pb-2">
              <span className="flex items-center gap-1.5">
                <span>YOUTUBE PUBLISHING DESTINATION</span>
              </span>
              <div className="flex items-center gap-2">
                {ytAccounts.length > 0 ? (
                  <div className="flex items-center gap-1.5 text-[10px] font-mono bg-[#0d0f12] px-2 py-0.5 border border-[#ff1e1e]/40">
                    <span className="text-[#88909e]">Target:</span>
                    <select
                      value={
                        ytAccounts.find(a => a.is_active || a.name.toLowerCase() === (channelInfo?.channel_title || state?.youtube_channel || '').toLowerCase())?.id ||
                        ytAccounts[0]?.id || ''
                      }
                      onChange={(e) => handleAccountSwitch(e.target.value)}
                      disabled={isSwitchingAccount}
                      className="bg-transparent text-[#ff1e1e] font-bold outline-none cursor-pointer border-none py-0 text-[10px]"
                      title="Switch YouTube account destination"
                    >
                      {ytAccounts.map((acc) => (
                        <option key={acc.id} value={acc.id} className="bg-[#14171d] text-white">
                          {acc.name}
                        </option>
                      ))}
                    </select>
                    {isSwitchingAccount && <span className="text-yellow-400 animate-pulse text-[9px]">...</span>}
                  </div>
                ) : channelInfo?.channel_title ? (
                  <span className="text-white font-mono text-[10px] bg-[#0d0f12] px-2 py-0.5 border border-[#ff1e1e]/40">
                    Target: <strong className="text-[#ff1e1e]">{channelInfo.channel_title}</strong>
                  </span>
                ) : null}

                {state?.auto_upload ? (
                  <span className="text-[#ff1e1e] font-mono text-[10px] bg-[#ff1e1e]/15 px-2 py-0.5 border border-[#ff1e1e]/40 flex items-center gap-1 font-bold">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#ff1e1e] animate-pulse"></span>
                    AUTO-UPLOAD ACTIVE
                  </span>
                ) : (
                  <span className="text-[#00e676] font-mono text-[10px] bg-[#00e676]/10 px-2 py-0.5 border border-[#00e676]/30 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#00e676]"></span>
                    SAFE CONFIRMATION MODE
                  </span>
                )}
              </div>
            </div>

            <div className="p-2.5 bg-[#0d0f12] border border-[#262b34] space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-mono">
                <div className="flex items-center gap-1.5 text-white">
                  <Calendar className="w-3.5 h-3.5 text-yellow-400" />
                  <span>Assigned Slot (1 Post/Day): <strong className="text-[#00e676]">{clip.scheduled_slot_display}</strong></span>
                </div>
                <span className="text-[10px] text-[#88909e]">EST (America/New_York)</span>
              </div>

              {/* 7-Day Auto-Scheduler Queue Preview */}
              {schedulePreview?.calendar && (
                <div className="pt-2 border-t border-[#262b34] space-y-1.5">
                  <div className="text-[10px] text-[#88909e] uppercase font-mono flex items-center justify-between">
                    <span>Account Schedule Queue (Anti-Overlap Verified)</span>
                    <span className="text-[9px] text-[#00e676]">Target: 1 Post/Day</span>
                  </div>
                  <div className="grid grid-cols-7 gap-1 text-[10px] font-mono">
                    {schedulePreview.calendar.map((item, idx) => {
                      const isAssignedToThisClip = clip.scheduled_slot_display && (
                        clip.scheduled_slot_display.includes(item.display_date) ||
                        clip.scheduled_slot_display.includes(item.day_name)
                      );
                      const isOccupied = item.status === 'OCCUPIED';

                      return (
                        <div
                          key={idx}
                          className={`p-1.5 border text-center transition-none ${
                            isAssignedToThisClip
                              ? 'bg-[#00e676]/15 border-[#00e676] text-[#00e676]'
                              : isOccupied
                              ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
                              : 'bg-[#14171d] border-[#262b34] text-[#88909e]'
                          }`}
                        >
                          <div className="font-bold text-white text-[11px]">{item.day_name.slice(0, 3)}</div>
                          <div className="text-[9px] text-[#88909e]">{item.display_date.split(', ')[1]}</div>
                          <div className="text-[10px] font-bold mt-1 text-white">{item.optimal_time_display}</div>
                          <div className="text-[8px] uppercase mt-1 tracking-tight">
                            {isAssignedToThisClip
                              ? '★ ASSIGNED'
                              : isOccupied
                              ? 'OCCUPIED'
                              : 'OPEN'}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="text-[10px] text-yellow-400 font-mono">
                🔒 Safe Mode: No video will be uploaded to your channel without your explicit confirmation.
              </div>
            </div>

            {clip.youtube_url && (
              <div className="p-2.5 bg-[#00e676]/10 border border-[#00e676]/30 text-xs font-mono text-[#00e676] flex items-center justify-between">
                <span>Published: {clip.youtube_url}</span>
                <a
                  href={clip.youtube_url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline flex items-center gap-1"
                >
                  Open Short <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            )}

            {actionStatus && (
              <div className="text-xs font-mono text-yellow-400 bg-yellow-500/10 p-2 border border-yellow-500/20">
                {actionStatus}
              </div>
            )}

            {/* Action Buttons */}
            {clip.status === 'PENDING_REVIEW' && (
              <div className="grid grid-cols-3 gap-2 pt-2">
                <button
                  onClick={handleApprove}
                  className="bg-[#00e676] hover:bg-[#00c853] text-black font-mono font-bold text-xs py-2 flex items-center justify-center gap-1 transition-none"
                >
                  <Check className="w-3.5 h-3.5" />
                  APPROVE & SCHEDULE
                </button>

                <button
                  onClick={handleUploadNow}
                  className="bg-[#ff1e1e] hover:bg-[#d01818] text-white font-mono font-bold text-xs py-2 flex items-center justify-center gap-1 transition-none"
                >
                  <Upload className="w-3.5 h-3.5" />
                  UPLOAD NOW
                </button>

                <button
                  onClick={handleReject}
                  className="bg-[#262b34] hover:bg-red-900/50 hover:text-red-400 text-[#88909e] font-mono text-xs py-2 flex items-center justify-center gap-1 transition-none"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  REJECT & PURGE
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}