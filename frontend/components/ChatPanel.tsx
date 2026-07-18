'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  symbol?: string;
}

export interface ChatHandle {
  pushMessage: (role: 'user' | 'assistant', content: string, symbol?: string) => void;
}

interface Props {
  onSelectSymbol: (s: string) => void;
  onSnapshotCapture: () => Promise<void>;
}

function renderContent(text: string) {
  // Minimal markdown: **bold** + line breaks.
  return text.split('\n').map((line, li) => (
    <p key={li} className="whitespace-pre-wrap">
      {line.split(/(\*\*[^*]+\*\*)/g).map((tok, i) =>
        tok.startsWith('**') && tok.endsWith('**') ? (
          <strong key={i} className="text-white">{tok.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{tok}</span>
        )
      )}
    </p>
  ));
}

const ChatPanel = forwardRef<ChatHandle, Props>(function ChatPanel(
  { onSelectSymbol, onSnapshotCapture },
  ref
) {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: 'assistant',
      content:
        "Hi — I'm your Quant AI Terminal assistant. Ask me about any market (e.g. \"Analyze XAUUSD\"), " +
        'hit **⚡ Analyze** for a trade plan, or **📷 Snapshot & Analyze** to read the current chart.',
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    pushMessage: (role: 'user' | 'assistant', content: string, symbol?: string) => {
      setMessages((m) => [...m, { role, content, symbol }]);
    },
  }));

  useEffect(() => {
    fetch(`${API_URL}/api/v1/chat/suggestions`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setSuggestions(d.suggestions || []))
      .catch(() => setSuggestions([]));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async (text: string) => {
    const msg = text.trim();
    if (!msg || busy) return;
    setBusy(true);
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: msg }]);
    try {
      const res = await fetch(`${API_URL}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ message: msg }),
      });
      const d = await res.json();
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: d.reply, symbol: d.context?.symbol },
      ]);
      if (d.suggestions) setSuggestions(d.suggestions);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `⚠️ Chat error: ${e?.message || 'unreachable'}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const handleSnapshot = async () => {
    if (capturing) return;
    setCapturing(true);
    try {
      await onSnapshotCapture();
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `⚠️ Snapshot failed: ${e?.message || 'unreachable'}` },
      ]);
    } finally {
      setCapturing(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 border-t border-[#1e2433]">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1e2433]">
        <span className="text-blue-400">💬</span>
        <h2 className="text-sm font-semibold">AI Chat Assistant</h2>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm text-gray-200 ${
                m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-[#0d1117] border border-[#1e2433]'
              }`}
            >
              {renderContent(m.content)}
              {m.role === 'assistant' && m.symbol && (
                <button
                  onClick={() => onSelectSymbol(m.symbol!)}
                  className="mt-2 text-[11px] px-2 py-1 rounded bg-[#1e2433] hover:bg-[#2d3648] text-blue-300"
                >
                  📈 View {m.symbol} on chart
                </button>
              )}
            </div>
          </div>
        ))}
        {busy && <p className="text-xs text-gray-500 px-1">Assistant is typing…</p>}
      </div>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1 px-3 pb-2">
          {suggestions.slice(0, 4).map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="text-[11px] px-2 py-1 rounded-full border border-[#2d3648] text-gray-400 hover:text-white hover:border-blue-500"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="px-3 pb-3 border-t border-[#1e2433]">
        <button
          onClick={handleSnapshot}
          disabled={capturing}
          className="w-full mb-2 px-3 py-2 rounded text-sm font-semibold bg-purple-600 hover:bg-purple-700 disabled:opacity-50"
        >
          {capturing ? 'Capturing…' : '📷 Snapshot & Analyze'}
        </button>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a market, risk, or news…"
            className="flex-1 bg-[#0d1117] border border-[#1e2433] rounded px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy}
            className="px-3 py-2 rounded text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
});

export default ChatPanel;
