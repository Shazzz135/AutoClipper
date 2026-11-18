import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import Column1Peak from './components/Column1Peak';
import Column2Facecam from './components/Column2Facecam';
import Column3Speech from './components/Column3Speech';
import PreviewPage from './components/PreviewPage';
import { ArrowRight, CheckCircle2, Trash2 } from 'lucide-react';
import { sound } from './services/sound';

export default function App() {
  const [state, setState] = useState(null);
  const [view, setView] = useState('dashboard'); // 'dashboard' or 'preview'
  const [activeClipId, setActiveClipId] = useState(null);
  const activeClip = state?.active_clip;
  const seenPeakIdsRef = useRef(new Set());
  const isInitialLoadRef = useRef(true);

  useEffect(() => {
    // Connect WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    let ws = null;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setState(data);

          // Check if a new peak was detected to trigger the ping sound effect
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

          if (data.active_clip_id) {
            setActiveClipId(data.active_clip_id);
          }
        } catch (e) {
          console.error('WS parse error:', e);
        }
      };

      ws.onclose = () => {
        setTimeout(connect, 2000); // Reconnect on drop
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

  const isAllOk = state?.all_processes_ok;

  const handleDiscardClip = async () => {
    if (!activeClipId) return;
    const clipDisplayName = activeClip?.name || activeClip?.date || 'active clip';
    if (window.confirm(`Discard and purge clip [${clipDisplayName}]?`)) {
      try {
        await fetch(`/api/clips/${activeClipId}`, { method: 'DELETE' });
        setActiveClipId(null);
      } catch (err) {
        console.error(err);
      }
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-x-hidden bg-[#0d0f12]">
      {/* Top Telemetry Header */}
      <Header
        state={state}
        view={view}
        setView={setView}
        onTriggerTest={handleTriggerTest}
      />

      {/* Main Content Area */}
      <main className="flex-1 min-h-0 flex flex-col overflow-y-auto">
        {view === 'dashboard' ? (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Success Banner when all 3 processes are OK */}
            {activeClipId && (
              <div className="bg-[#14171d] border-b border-[#262b34] px-4 py-2 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2 text-xs font-mono text-[#00e676]">
                  <CheckCircle2 className="w-4 h-4 text-[#00e676]" />
                  <span>
                    PROCESSES COMPLETED: <strong>[{activeClip?.name || activeClip?.date || 'Ready'}]</strong> {activeClip?.title ? `"${activeClip.title}"` : ''} ready for review & upload.
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDiscardClip}
                    className="bg-[#262b34] hover:bg-red-950/60 hover:text-red-400 text-[#88909e] px-2.5 py-1 text-xs font-mono flex items-center gap-1 transition-none"
                    title="Discard and purge this clip"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    DISCARD
                  </button>
                  <button
                    onClick={() => setView('preview')}
                    className="bg-[#ff1e1e] hover:bg-[#d01818] text-white px-3 py-1 text-xs font-mono font-bold flex items-center gap-1.5 transition-none"
                  >
                    OPEN PREVIEW & UPLOAD PAGE
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* 3 Process Columns Layout */}
            <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 overflow-y-auto">
              <Column1Peak data={state?.col1} activeClipId={activeClipId} state={state} />
              <Column2Facecam data={state?.col2} />
              <Column3Speech data={state?.col3} />
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <PreviewPage
              clipId={activeClipId}
              onBack={() => setView('dashboard')}
              state={state}
            />
          </div>
        )}
      </main>
    </div>
  );
}
