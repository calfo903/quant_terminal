'use client';

import { useEffect, useState } from 'react';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Session {
  name: string;
  color: string;
  start: number;
  end: number;
  active: boolean;
  progress: number;
}

export default function MarketSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [utc, setUtc] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/sessions`, { headers: authHeaders() });
        const d = await res.json();
        if (!cancelled) {
          setSessions(d.sessions || []);
          setUtc(d.current_utc || '');
        }
      } catch {
        /* offline */
      }
    };
    load();
    const id = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="flex items-center gap-3 bg-[#161b22] rounded-lg px-3 py-2 border border-[#1e2433] text-xs">
      <span className="text-gray-500">Sessions (UTC)</span>
      {sessions.map((s) => (
        <div key={s.name} className="flex flex-col items-center" style={{ minWidth: 64 }}>
          <div
            className="px-2 py-1 rounded text-center w-full"
            style={{
              background: s.active ? s.color : 'transparent',
              border: `1px solid ${s.color}`,
              color: s.active ? '#0a0e1a' : s.color,
              fontWeight: s.active ? 700 : 400,
            }}
          >
            {s.name}
          </div>
          {s.active && (
            <div className="h-0.5 mt-0.5 rounded bg-gray-600 w-full overflow-hidden">
              <div className="h-full" style={{ width: `${Math.round(s.progress * 100)}%`, background: s.color }} />
            </div>
          )}
        </div>
      ))}
      <span className="text-gray-400 ml-auto font-mono">{utc}</span>
    </div>
  );
}
