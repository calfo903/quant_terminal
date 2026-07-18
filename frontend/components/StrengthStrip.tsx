'use client';

import { useEffect, useState } from 'react';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Strength {
  strength: number;
  bias: string;
  trend: string;
  adx: number;
  rsi: number;
  macd: { macd: number; signal: number; hist: number };
  bollinger: { pct_b: number; bandwidth: number };
  atr_pct: number;
  volume_ratio: number;
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] text-gray-500">{label}</span>
      <span className={`text-sm font-mono ${color || 'text-gray-200'}`}>{value}</span>
    </div>
  );
}

export default function StrengthStrip({ symbol, timeframe }: { symbol: string; timeframe: string }) {
  const [d, setD] = useState<Strength | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/charts/${symbol}/strength?timeframe=${timeframe}`, { headers: authHeaders() });
        if (res.ok) {
          const j = await res.json();
          if (!cancelled) setD(j);
        }
      } catch {
        /* offline */
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol, timeframe]);

  if (!d) return <div className="text-xs text-gray-500 px-1 py-2">Loading market strength…</div>;

  const biasColor =
    d.bias === 'bullish' ? 'text-emerald-400' : d.bias === 'bearish' ? 'text-red-400' : 'text-gray-400';

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 bg-[#161b22] rounded-lg px-4 py-2 border border-[#1e2433]">
      <div className="flex flex-col">
        <span className="text-[10px] text-gray-500">Strength</span>
        <span className={`text-lg font-bold ${biasColor}`}>{d.strength}/100</span>
      </div>
      <Metric label="Bias" value={d.bias} color={biasColor} />
      <Metric label="Trend" value={d.trend} />
      <Metric label="ADX" value={String(d.adx)} color={d.adx >= 25 ? 'text-emerald-400' : 'text-gray-400'} />
      <Metric label="RSI" value={String(d.rsi)} />
      <Metric
        label="MACD"
        value={String(d.macd.hist)}
        color={d.macd.hist >= 0 ? 'text-emerald-400' : 'text-red-400'}
      />
      <Metric label="BB %B" value={String(d.bollinger.pct_b)} />
      <Metric label="ATR %" value={`${(d.atr_pct * 100).toFixed(2)}`} />
      <Metric label="Vol ×" value={String(d.volume_ratio)} />
    </div>
  );
}
