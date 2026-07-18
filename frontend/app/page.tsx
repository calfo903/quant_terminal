'use client';

import React, { useState, useRef, useEffect } from 'react';
import { authHeaders } from '../lib/api';
import TradingViewChart, { type ChartType, type Plan } from '../components/TradingViewChart';
import ChartToolbar from '../components/ChartToolbar';
import MarketSessions from '../components/MarketSessions';
import StrengthStrip from '../components/StrengthStrip';
import NewsSidebar from '../components/NewsSidebar';
import ChatPanel, { type ChatHandle } from '../components/ChatPanel';
import { ImageUpload } from '../components/ImageUpload';
import { AnalysisResults } from '../components/AnalysisResults';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function formatPlanReply(p: Plan): string {
  if (!p || p.entry == null) {
    return `**${p?.instrument ?? 'symbol'}** — no tradable plan (${p?.patterns?.[0] ?? 'no history'}).`;
  }
  const lines = [
    `**Trade plan — ${p.instrument} (${p.timeframe})**`,
    `• Direction: **${p.direction.toUpperCase()}** (signal ${p.signal}, conf ${p.confidence.toFixed(2)}, RR ${p.risk_reward.toFixed(1)})`,
    `• Entry ${p.entry} | SL ${p.stop_loss} | TP ${p.take_profit}`,
  ];
  if (p.support != null) lines.push(`• Support ~${p.support} | Resistance ~${p.resistance}`);
  if (p.forecast?.length) lines.push('• Forecast line projected forward (dashed on chart).');
  const pat = (p.patterns || []).filter((x) => !x.startsWith('Support') && !x.startsWith('Resistance'));
  if (pat.length) lines.push(`• Formation: ${pat.join(', ')}`);
  lines.push('Drawn on the chart. Not financial advice.');
  return lines.join('\n');
}

function FeedStatus() {
  const [sources, setSources] = useState<any[]>([]);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/status`, { headers: authHeaders() });
        if (res.ok) {
          const d = await res.json();
          if (!cancelled) setSources(d.sources || []);
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
  }, []);
  const dot = (s: string) => (s === 'streaming' ? 'bg-emerald-500' : s === 'stale' ? 'bg-amber-500' : 'bg-gray-600');
  return (
    <div className="flex items-center gap-3 text-xs">
      {sources.map((src) => (
        <span key={src.name} className="flex items-center gap-1 text-gray-400" title={src.status}>
          <span className={`w-2 h-2 rounded-full ${dot(src.status)}`} />
          {src.name}
        </span>
      ))}
    </div>
  );
}

export default function TradingDashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');
  const [selectedTimeframe, setSelectedTimeframe] = useState('5m');
  const [chartType, setChartType] = useState<ChartType>('candlestick');
  const [showMA, setShowMA] = useState(false);
  const [showEMA, setShowEMA] = useState(false);
  const [showRSI, setShowRSI] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showStrength, setShowStrength] = useState(false);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  const [showImageUpload, setShowImageUpload] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);

  const chatRef = useRef<ChatHandle>(null);

  const handleAnalysisComplete = (result: any) => {
    setAnalysisResult(result);
    setShowImageUpload(false);
    if (result?.symbol) setSelectedSymbol(result.symbol);
  };

  const toggle = (key: 'showMA' | 'showEMA' | 'showRSI' | 'showVolume' | 'showStrength') => {
    if (key === 'showMA') setShowMA((v) => !v);
    if (key === 'showEMA') setShowEMA((v) => !v);
    if (key === 'showRSI') setShowRSI((v) => !v);
    if (key === 'showVolume') setShowVolume((v) => !v);
    if (key === 'showStrength') setShowStrength((v) => !v);
  };

  const handleAnalyze = async () => {
    if (analyzing) return;
    setAnalyzing(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/charts/${selectedSymbol}/plan?timeframe=${selectedTimeframe}`,
        { method: 'POST', headers: authHeaders() }
      );
      if (!res.ok) throw new Error(`Analyze ${res.status}`);
      const p: Plan = await res.json();
      setPlan(p);
      chatRef.current?.pushMessage('assistant', formatPlanReply(p), p.instrument);
    } catch (e: any) {
      chatRef.current?.pushMessage('assistant', `⚠️ Analyze failed: ${e?.message || 'unreachable'}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const captureChart = (): string | null => {
    const el = document
      .getElementById('trading-chart-container')
      ?.querySelector('canvas') as HTMLCanvasElement | null;
    return el ? el.toDataURL('image/png') : null;
  };

  const handleSnapshot = async () => {
    const dataUrl = captureChart();
    if (!dataUrl) throw new Error('Could not capture chart canvas');
    chatRef.current?.pushMessage('user', `📷 Snapshot: ${selectedSymbol}`);
    const res = await fetch(`${API_URL}/api/v1/chat/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ image: dataUrl, symbol: selectedSymbol }),
    });
    if (!res.ok) throw new Error(`Snapshot ${res.status}`);
    const d = await res.json();
    if (d.context?.symbol) setSelectedSymbol(d.context.symbol);
    if (d.plan) setPlan(d.plan);
    chatRef.current?.pushMessage('assistant', d.reply, d.context?.symbol);
  };

  const chartEl = (
    <TradingViewChart
      symbol={selectedSymbol}
      timeframe={selectedTimeframe}
      chartType={chartType}
      showMA={showMA}
      showEMA={showEMA}
      showRSI={showRSI}
      showVolume={showVolume}
      showStrength={showStrength}
      plan={plan}
    />
  );

  const toolbar = (
    <ChartToolbar
      symbol={selectedSymbol}
      timeframe={selectedTimeframe}
      chartType={chartType}
      showMA={showMA}
      showEMA={showEMA}
      showRSI={showRSI}
      showVolume={showVolume}
      showStrength={showStrength}
      onSymbolChange={setSelectedSymbol}
      onTimeframeChange={setSelectedTimeframe}
      onChartTypeChange={setChartType}
      onToggle={toggle}
      onAnalyze={handleAnalyze}
      analyzing={analyzing}
      fullscreen={fullscreen}
      onToggleFullscreen={() => setFullscreen((v) => !v)}
    />
  );

  return (
    <div className="min-h-screen flex flex-col bg-[#0a0e1a] text-white">
      <header className="border-b border-[#1e2433] bg-[#0d1117] px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              ⚡ Quant AI Terminal
            </h1>
            <FeedStatus />
          </div>
          <button
            onClick={() => setShowImageUpload(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium transition-colors"
          >
            <span>Analyze Image</span>
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Main content: charts tool */}
        <main className="flex-1 min-w-0 flex flex-col p-4 space-y-3 overflow-y-auto">
          {toolbar}
          <MarketSessions />
          <div className="h-[700px] shrink-0">{chartEl}</div>
          {showStrength && (
            <StrengthStrip symbol={selectedSymbol} timeframe={selectedTimeframe} />
          )}
        </main>

        {/* Right sidebar: news + chat */}
        <aside className="w-[360px] shrink-0 border-l border-[#1e2433] flex flex-col min-h-0 bg-[#0d1117]">
          <div className="flex-1 min-h-0">
            <NewsSidebar onSelectSymbol={setSelectedSymbol} selectedSymbol={selectedSymbol} />
          </div>
          <div className="h-[460px] shrink-0">
            <ChatPanel ref={chatRef} onSelectSymbol={setSelectedSymbol} onSnapshotCapture={handleSnapshot} />
          </div>
        </aside>
      </div>

      {/* Fullscreen chart overlay */}
      {fullscreen && (
        <div className="fixed inset-0 z-50 bg-[#0a0e1a] flex flex-col p-4">
          {toolbar}
          <MarketSessions />
          <div className="flex-1 min-h-0 mt-3">{chartEl}</div>
        </div>
      )}

      {showImageUpload && (
        <ImageUpload
          onAnalysisComplete={handleAnalysisComplete}
          onClose={() => setShowImageUpload(false)}
        />
      )}

      {analysisResult && (
        <AnalysisResults
          result={analysisResult}
          onImportToChart={() => {}}
          onClose={() => setAnalysisResult(null)}
        />
      )}
    </div>
  );
}
