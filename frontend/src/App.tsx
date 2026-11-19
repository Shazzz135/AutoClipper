import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import Column1Peak from './components/Column1Peak';
import ClipStudio from './components/ClipStudio';
import PreviewPage from './components/PreviewPage';
import { ArrowRight, CheckCircle2, Trash2, ExternalLink, AlertTriangle, RefreshCw } from 'lucide-react';
import { sound } from './services/sound';

export default function App() {
  const [state, setState] = useState(null);
  const [view, setView] = useState('dashboard'); // 'dashboard' or 'preview'
  const [activeClipId, setActiveClipId] = useState(null);
  const activeClip = state?.active_clip;
  const seenPeakIdsRef = useRef(new Set());
  const isInitialLoadRef = useRef(true);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    let ws = null;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setState(data);

          const currentPeaks = data?.col1?.detected_peaks || [];
          let hasNewPeak = false;

          currentPeaks.forEach((p) => {
            if (p.peak_id && !seenPeakIdsRef.current.has(p.peak_id)) {
              seenPeakIdsRef.current.add(p.peak_id);
              if (!isInitialLoadRef.current) {
                hasNewPeak = true;
              }
            }
          });
          isInitialLoadRef.current = false;

          if (hasNewPeak) {
            sound.playPing();
          }

          setActiveClipId(data.active_clip_id || null);
        } catch (e) {
          console.error('WS parse error:', e);
        }
      };

      ws.onclose = () => {
        setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
    };
  }, []);

  const handleTriggerTest = async () => {
    try {
      await fetch('/api/trigger_test_peak', { method: 'POST' });
    } catch (err) {
      console.error(err);
    }
  };

  const handleDiscardClip = async () => {
    if (!activeClipId) return;
    const clipDisplayName = activeClip?.name || activeClip?.date || 'active clip';
    if (window.confirm(`Discard and purge clip [${clipDisplayName}] and free SSD space?`)) {
      const idToPurge = activeClipId;
      setActiveClipId(null);
      try {
        await fetch(`/api/clips/${idToPurge}/reject`, { method: 'POST' });
      } catch (err) {
        console.error(err);
      }
    }
  };

  const handleOpenPreview = () => {
    if (activeClip?.clip_created) {
      setView('preview');
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-x-hidden bg-[#0d0f12]">
      {/* Top Telemetry Header */}
      <Header
        state={state}
        view={view}
        setView={setView}
        onOpenPreview={handleOpenPreview}
        isBuildingPreview={false}
        onTriggerTest={handleTriggerTest}
      />

      {/* Main Content Area */}
      <main className="flex-1 min-h-0 flex flex-col overflow-y-auto">
        {view === 'dashboard' ? (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Banner when 9:16 Short has been created and is ready on Preview & Post page */}
            {(activeClipId && activeClip && activeClip.clip_created && activeClip.status !== 'REJECTED' && activeClip.status !== 'DISCARDED') && (
              <div className={`border-b px-4 py-2 flex flex-col sm:flex-row items-center justify-between gap-2 shrink-0 ${
                activeClip.status === 'UPLOADED'
                  ? 'bg-[#00e676]/15 border-[#00e676]/50'
                  : activeClip.status === 'UPLOAD_ERROR'
                  ? 'bg-red-950/40 border-red-500/50'
                  : activeClip.status === 'UPLOADING'
                  ? 'bg-yellow-500/15 border-yellow-500/40'
                  : 'bg-[#14171d] border-[#262b34]'
              }`}>
                <div className="flex items-center gap-2 text-xs font-mono">
                  {activeClip.status === 'UPLOADED' ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-[#00e676] shrink-0" />
                      <span className="text-[#00e676]">
                        🎉 <strong>UPLOAD SUCCESSFUL!</strong> Clip <strong>[{activeClip?.name || 'Clip'}]</strong> is uploaded to YouTube Shorts!
                      </span>
                    </>
                  ) : activeClip.status === 'UPLOAD_ERROR' ? (
                    <>
                      <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                      <span className="text-red-300">
                        ⚠️ <strong>UPLOAD FAILED:</strong> {activeClip?.upload_error || 'Network error during upload.'}
                      </span>
                    </>
                  ) : activeClip.status === 'UPLOADING' ? (
                    <>
                      <RefreshCw className="w-4 h-4 text-yellow-400 animate-spin shrink-0" />
                      <span className="text-yellow-300">
                        ⏳ <strong>UPLOADING DIRECTLY TO YOUTUBE SHORTS...</strong> (resumable chunks with auto-retry)
                      </span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-[#00e676] shrink-0" />
                      <span className="text-[#00e676]">
                        9:16 SHORT READY: <strong>[{activeClip?.name || activeClip?.date || 'Ready'}]</strong> {activeClip?.title ? `"${activeClip.title}"` : ''} ({activeClip.duration_sec}s, {activeClip.size_mb} MB) ready for download & YouTube upload.
                      </span>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {activeClip.status === 'UPLOADED' && activeClip.youtube_url && (
                    <a
                      href={activeClip.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      className="bg-[#00e676] hover:bg-[#00c853] text-black px-3 py-1 text-xs font-mono font-bold flex items-center gap-1.5 transition-none cursor-pointer"
                    >
                      WATCH SHORTS
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                  <button
                    onClick={handleDiscardClip}
                    className="bg-[#262b34] hover:bg-red-950/60 hover:text-red-400 text-[#88909e] px-2.5 py-1 text-xs font-mono flex items-center gap-1 transition-none cursor-pointer"
                    title={activeClip.status === 'UPLOADED' ? 'Close and free SSD space' : 'Discard and purge this clip'}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {activeClip.status === 'UPLOADED' ? 'CLOSE' : 'DISCARD'}
                  </button>
                  {activeClip.status !== 'UPLOADED' && (
                    <button
                      onClick={() => setView('preview')}
                      className={`${
                        activeClip.status === 'UPLOAD_ERROR'
                          ? 'bg-red-600 hover:bg-red-500'
                          : 'bg-[#ff1e1e] hover:bg-[#d01818]'
                      } text-white px-3 py-1 text-xs font-mono font-bold flex items-center gap-1.5 transition-none cursor-pointer`}
                    >
                      {activeClip.status === 'UPLOAD_ERROR' ? 'OPEN & RETRY' : 'OPEN PREVIEW & YOUTUBE UPLOAD'}
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Column 1 (Peak Detection) + Unified 16:9 Clip Studio (Replaces Columns 2 & 3) */}
            <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 overflow-y-auto">
              <Column1Peak data={state?.col1} activeClipId={activeClipId} state={state} />
              <ClipStudio
                state={state}
                activeClip={activeClip}
                activeClipId={activeClipId}
                onClipCreated={() => setView('preview')}
                onDiscardClip={handleDiscardClip}
              />
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <PreviewPage
              clipId={activeClipId}
              onBack={() => setView('dashboard')}
              onDiscard={() => setActiveClipId(null)}
              state={state}
            />
          </div>
        )}
      </main>
    </div>
  );
}
