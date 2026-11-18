import React, { useState, useEffect } from 'react';
import { Mic, FileText, CheckCircle2, Terminal, Edit3, Check } from 'lucide-react';

export default function Column3Speech({ data }) {
  const status = data?.status || 'IDLE';
  const rawTranscript = data?.current_transcript || [];
  const censoredCount = data?.censored_count || 0;
  const renderTime = data?.last_render_time_sec || 0;
  const logs = data?.logs || [];

  const [editableTranscript, setEditableTranscript] = useState([]);
  const [editingIndex, setEditingIndex] = useState(null);

  useEffect(() => {
    setEditableTranscript(rawTranscript);
  }, [rawTranscript]);

  const handleTextChange = (index, newText) => {
    // Enforce max 4 words per row (no character limit)
    const words = newText.trim().split(/\s+/).filter(Boolean);
    if (words.length > 4) {
      newText = words.slice(0, 4).join(' ');
    }
    const updated = [...editableTranscript];
    updated[index] = { ...updated[index], text: newText };
    setEditableTranscript(updated);
  };

  const handleSaveTranscript = async () => {
    setEditingIndex(null);
    try {
      await fetch('/api/transcript/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: editableTranscript })
      });
    } catch (err) {
      console.error(err);
    }
  };

  const getStatusBg = (s) => {
    if (s === 'COMPLETED' || s === 'OK') return 'bg-[#00e676]/20 text-[#00e676] border border-[#00e676]/30';
    if (s.includes('TRANSCRIBING') || s.includes('RENDERING')) return 'bg-purple-500/20 text-purple-400 border border-purple-500/30';
    return 'bg-[#262b34] text-[#88909e]';
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0d0f12]">
      {/* Column Title */}
      <div className="p-3 border-b border-[#262b34] bg-[#14171d] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Mic className="w-4 h-4 text-purple-400" />
          <span className="font-bold text-xs uppercase tracking-wider text-white">
            COLUMN 3: SPEECH & RENDERING
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
            <div className="text-[10px] text-[#88909e] uppercase">STT Model</div>
            <div className="text-base font-bold font-mono text-white">small.en <span className="text-[10px] text-[#88909e]">INT8</span></div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Text Censored</div>
            <div className="text-base font-bold font-mono text-white">{censoredCount} <span className="text-[10px] text-[#88909e]">words</span></div>
          </div>
          <div className="border border-[#262b34] bg-[#14171d] p-2">
            <div className="text-[10px] text-[#88909e] uppercase">Render Time</div>
            <div className="text-base font-bold font-mono text-white">{renderTime} <span className="text-[10px] text-[#88909e]">sec</span></div>
          </div>
        </div>

        {/* Editable Transcript Stream */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center justify-between">
            <span className="flex items-center gap-1">
              <FileText className="w-3 h-3 text-purple-400" />
              EDITABLE TRANSCRIPT STREAM (MAX 4 WORDS PER ROW)
            </span>
            {editingIndex !== null && (
              <button
                onClick={handleSaveTranscript}
                className="bg-[#00e676] text-black px-1.5 py-0.5 text-[9px] font-bold flex items-center gap-1"
              >
                <Check className="w-2.5 h-2.5" /> SAVE EDITS
              </button>
            )}
          </div>

          <div className="h-36 overflow-y-auto text-[11px] font-mono space-y-1.5 bg-[#0d0f12] p-1.5 border border-[#262b34]">
            {editableTranscript.length === 0 ? (
              <div className="text-[#88909e] italic">No active audio transcription yet.</div>
            ) : (
              editableTranscript.map((t, i) => (
                <div key={i} className="flex items-center gap-1.5 border-b border-[#262b34]/40 pb-1">
                  <span className="text-purple-400 text-[10px] shrink-0 font-bold">
                    [{t.start}s - {t.end}s]
                  </span>
                  <input
                    type="text"
                    value={t.text}
                    onFocus={() => setEditingIndex(i)}
                    onChange={(e) => handleTextChange(i, e.target.value)}
                    placeholder="Max 4 words"
                    className="flex-1 bg-[#14171d] border border-[#262b34] focus:border-purple-400 px-1.5 py-0.5 text-xs text-white font-mono outline-none"
                  />
                </div>
              ))
            )}
          </div>
        </div>

        {/* Subtitle Rule Verification Box */}
        <div className="border border-[#262b34] bg-[#14171d] p-2 text-[11px] font-mono space-y-1">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1">
            SUBTITLE SPECIFICATIONS
          </div>
          <div className="flex items-center gap-1.5 text-white">
            <CheckCircle2 className="w-3 h-3 text-[#00e676]" />
            <span>Chunking: Max 4 words per row (No character limit)</span>
          </div>
          <div className="flex items-center gap-1.5 text-white">
            <CheckCircle2 className="w-3 h-3 text-[#00e676]" />
            <span>Vertical Placement: 20% vertical height (384px from bottom)</span>
          </div>
          <div className="flex items-center gap-1.5 text-white">
            <CheckCircle2 className="w-3 h-3 text-[#00e676]" />
            <span>Karaoke Accent: Active spoken word turns <strong className="text-[#ff1e1e]">RED</strong></span>
          </div>
          <div className="flex items-center gap-1.5 text-white">
            <CheckCircle2 className="w-3 h-3 text-[#00e676]" />
            <span>Censorship: Text masked (f***), audio 100% raw</span>
          </div>
        </div>

        {/* Terminal Logs */}
        <div className="border border-[#262b34] bg-[#14171d] p-2">
          <div className="text-[10px] font-bold text-[#88909e] uppercase mb-1.5 flex items-center gap-1">
            <Terminal className="w-3 h-3" />
            RENDERING & STT LOGS
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
