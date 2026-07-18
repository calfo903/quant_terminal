'use client';

import { useEffect, useRef, useState } from 'react';
import type { ChartType } from './TradingViewChart';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SymbolCatalog {
  crypto: string[];
  forex_majors: string[];
  forex_minors: string[];
  commodities: string[];
}

interface Props {
  symbol: string;
  timeframe: string;
  chartType: ChartType;
  showMA: boolean;
  showEMA: boolean;
  showRSI: boolean;
  showVolume: boolean;
  showStrength: boolean;
  onSymbolChange: (s: string) => void;
  onTimeframeChange: (t: string) => void;
  onChartTypeChange: (t: ChartType) => void;
  onToggle: (key: 'showMA' | 'showEMA' | 'showRSI' | 'showVolume' | 'showStrength') => void;
  onAnalyze: () => void;
  analyzing?: boolean;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
}

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'];
const CHART_TYPES: { id: ChartType; label: string }[] = [
  { id: 'candlestick', label: 'Candles' },
  { id: 'bars', label: 'Bars' },
  { id: 'line', label: 'Line' },
  { id: 'area', label: 'Area' },
];

export default function ChartToolbar({
  symbol,
  timeframe,
  chartType,
  showMA,
  showEMA,
  showRSI,
  showVolume,
  showStrength,
  onSymbolChange,
  onTimeframeChange,
  onChartTypeChange,
  onToggle,
  onAnalyze,
  analyzing = false,
  fullscreen,
  onToggleFullscreen,
}: Props) {
  const [catalog, setCatalog] = useState<SymbolCatalog | null>(null);
  const [query, setQuery] = useState('');
  const [price, setPrice] = useState<number | null>(null);
  const [feedAt, setFeedAt] = useState<number | null>(null);
  const selectRef = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/charts/symbols`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setCatalog(d))
      .catch(() => setCatalog(null));
  }, []);

  // Lightweight live price ticker + feed-status indicator for the current symbol.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/charts/${symbol}/latest`, { headers: authHeaders() });
        if (res.ok) {
          const d = await res.json();
          if (!cancelled && d?.price != null) {
            setPrice(Number(d.price));
            setFeedAt(d.received_at != null ? Number(d.received_at) : null);
          }
        }
      } catch {
        /* offline */
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [symbol]);

  const filteredCatalog = (() => {
    if (!catalog || !query) return catalog;
    const q = query.toUpperCase();
    const f = (arr: string[] = []) => arr.filter((s) => s.includes(q));
    return {
      crypto: f(catalog.crypto),
      forex_majors: f(catalog.forex_majors),
      forex_minors: f(catalog.forex_minors),
      commodities: f(catalog.commodities),
    };
  })();

  const commitQuery = () => {
    const v = query.trim().toUpperCase();
    if (v) onSymbolChange(v);
  };

  const feedAge = feedAt != null ? Date.now() / 1000 - feedAt : null;
  const feedOk = feedAge != null && feedAge < 30;
  const feedStale = feedAge != null && feedAge >= 30 && feedAge < 120;
  const feedDot = feedOk ? 'bg-emerald-500' : feedStale ? 'bg-amber-500' : 'bg-gray-600';

  const IndicatorBtn = ({ active, label, k }: { active: boolean; label: string; k: any }) => (
    <button
      onClick={() => onToggle(k)}
      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
        active ? 'bg-blue-600 text-white' : 'bg-[#0d1117] text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-wrap items-center gap-3 bg-[#161b22] rounded-lg p-3 border border-[#1e2433]">
      {/* Symbol selection */}
      <div className="flex items-center gap-2">
        <select
          ref={selectRef}
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="bg-[#0d1117] border border-[#1e2433] rounded px-3 py-1 text-sm"
        >
          <option value={symbol}>{symbol}</option>
          {catalog?.crypto.map((s) => (
            <option key={`c-${s}`} value={s}>{s}</option>
          ))}
          <optgroup label="Forex Majors">
            {catalog?.forex_majors.map((s) => (
              <option key={`fm-${s}`} value={s}>{s}</option>
            ))}
          </optgroup>
          <optgroup label="Forex Minors">
            {catalog?.forex_minors.map((s) => (
              <option key={`fn-${s}`} value={s}>{s}</option>
            ))}
          </optgroup>
          <optgroup label="Commodities">
            {catalog?.commodities.map((s) => (
              <option key={`co-${s}`} value={s}>{s}</option>
            ))}
          </optgroup>
        </select>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && commitQuery()}
          placeholder="Search / type symbol…"
          className="bg-[#0d1117] border border-[#1e2433] rounded px-3 py-1 text-sm w-44"
        />

        {price != null && (
          <span className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${feedDot}`} title={feedOk ? 'Live feed' : feedStale ? 'Feed stale' : 'No feed'} />
            <span className="text-sm font-mono text-emerald-400">
              {price.toLocaleString(undefined, { maximumFractionDigits: price < 10 ? 4 : 2 })}
            </span>
          </span>
        )}
      </div>

      {/* Timeframe */}
      <div className="flex space-x-1">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => onTimeframeChange(tf)}
            className={`px-3 py-1 rounded text-xs ${
              timeframe === tf ? 'bg-blue-600 text-white' : 'bg-[#0d1117] text-gray-400 hover:text-white'
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* Chart type */}
      <div className="flex space-x-1">
        {CHART_TYPES.map((ct) => (
          <button
            key={ct.id}
            onClick={() => onChartTypeChange(ct.id)}
            className={`px-3 py-1 rounded text-xs ${
              chartType === ct.id ? 'bg-purple-600 text-white' : 'bg-[#0d1117] text-gray-400 hover:text-white'
            }`}
          >
            {ct.label}
          </button>
        ))}
      </div>

      {/* Indicators */}
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-500 mr-1">Indicators:</span>
        <IndicatorBtn active={showMA} label="MA" k="showMA" />
        <IndicatorBtn active={showEMA} label="EMA" k="showEMA" />
        <IndicatorBtn active={showRSI} label="RSI" k="showRSI" />
        <IndicatorBtn active={showStrength} label="Str" k="showStrength" />
        <IndicatorBtn active={showVolume} label="Vol" k="showVolume" />
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <button
          onClick={onAnalyze}
          disabled={analyzing}
          className="px-3 py-1 rounded text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50"
        >
          {analyzing ? 'Analyzing…' : '⚡ Analyze'}
        </button>
        <button
          onClick={onToggleFullscreen}
          className="px-3 py-1 rounded text-xs bg-[#0d1117] text-gray-300 hover:text-white border border-[#1e2433]"
          title="Toggle fullscreen"
        >
          {fullscreen ? '⤢ Exit' : '⤢ Full'}
        </button>
      </div>
    </div>
  );
}
