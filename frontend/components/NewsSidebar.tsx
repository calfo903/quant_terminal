'use client';

import { useEffect, useState, useCallback } from 'react';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface NewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  summary: string;
  category: string;
  importance: number;
  symbols: string[];
  published_at: string;
  sentiment: string;
  sentiment_score: number;
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const SENTIMENT_COLOR: Record<string, string> = {
  positive: 'bg-emerald-600',
  negative: 'bg-red-600',
  neutral: 'bg-slate-600',
  bullish: 'bg-emerald-600',
  bearish: 'bg-red-600',
};

export default function NewsSidebar({
  onSelectSymbol,
  selectedSymbol,
}: {
  onSelectSymbol: (s: string) => void;
  selectedSymbol: string;
}) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [source, setSource] = useState<string>('curated');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/news?limit=20`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`news ${res.status}`);
      const d = await res.json();
      setItems(d.items || []);
      setSource(d.source || 'curated');
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'failed');
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2433]">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <span className="text-red-400">●</span> Latest Important News
        </h2>
        <span className="text-[10px] text-gray-500 uppercase">{source}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1 min-h-0">
        {error && <p className="text-xs text-red-400 px-2 py-2">{error}</p>}
        {!error && items.length === 0 && (
          <p className="text-xs text-gray-500 px-2 py-2">Loading headlines…</p>
        )}

        {items.map((it) => {
          const sColor = SENTIMENT_COLOR[it.sentiment] || 'bg-slate-600';
          const imp = Math.min(5, Math.max(1, it.importance));
          return (
            <div
              key={it.id}
              className="rounded-md border border-[#1e2433] bg-[#0d1117] px-3 py-2 hover:border-[#2d3648] transition-colors"
            >
              <div className="flex items-start gap-2">
                <div className="flex flex-col items-center pt-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ background: `hsl(${imp * 18}, 80%, 55%)` }}
                    title={`importance ${imp}/5`}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-snug text-gray-100">{it.title}</p>
                  <div className="flex items-center flex-wrap gap-1 mt-1">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded text-white ${sColor}`}>
                      {it.sentiment}
                    </span>
                    <span className="text-[10px] text-gray-500">{it.source}</span>
                    <span className="text-[10px] text-gray-500">· {timeAgo(it.published_at)}</span>
                    <span className="text-[10px] text-gray-600 uppercase">{it.category}</span>
                  </div>

                  {it.symbols?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {it.symbols.map((sym) => (
                        <button
                          key={sym}
                          onClick={() => onSelectSymbol(sym)}
                          className={`text-[10px] px-1.5 py-0.5 rounded border ${
                            sym === selectedSymbol
                              ? 'border-blue-500 text-blue-300'
                              : 'border-[#2d3648] text-gray-400 hover:text-white'
                          }`}
                        >
                          {sym}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
