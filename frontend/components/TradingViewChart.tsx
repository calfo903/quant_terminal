'use client';

import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { authHeaders, wsUrl } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export type ChartType = 'candlestick' | 'line' | 'area' | 'bars';

export interface PlanPoint {
  time: number;
  value: number;
}

export interface Plan {
  instrument: string;
  timeframe: string;
  direction: 'long' | 'short' | 'neutral';
  signal: string;
  confidence: number;
  current_price: number | null;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number;
  forecast: PlanPoint[];
  patterns: string[];
  support: number | null;
  resistance: number | null;
  atr: number;
  generated_at?: string;
}

interface Props {
  symbol: string;
  timeframe: string;
  chartType?: ChartType;
  showMA?: boolean;
  showEMA?: boolean;
  showRSI?: boolean;
  showVolume?: boolean;
  showStrength?: boolean;
  plan?: Plan | null;
}

function toTime(t: number): UTCTimestamp {
  return t as UTCTimestamp;
}

export default function TradingViewChart({
  symbol,
  timeframe,
  chartType = 'candlestick',
  showMA = false,
  showEMA = false,
  showRSI = false,
  showVolume = false,
  showStrength = false,
  plan = null,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const strengthContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<any> | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const rsiRangeUnsubRef = useRef<(() => void) | null>(null);
  const strengthChartRef = useRef<IChartApi | null>(null);
  const strengthSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const strengthRangeUnsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#0a0e1a' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#1e2433' },
        horzLines: { color: '#1e2433' },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    let series: ISeriesApi<any>;
    if (chartType === 'line') {
      series = chart.addLineSeries({ color: '#3b82f6', lineWidth: 2, priceLineVisible: true });
    } else if (chartType === 'area') {
      series = chart.addAreaSeries({
        lineColor: '#3b82f6',
        topColor: 'rgba(59,130,246,0.4)',
        bottomColor: 'rgba(59,130,246,0.02)',
        lineWidth: 2,
      });
    } else if (chartType === 'bars') {
      series = chart.addBarSeries({
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      });
    } else {
      series = chart.addCandlestickSeries({
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      });
    }

    chartRef.current = chart;
    seriesRef.current = series;

    let volSeries: ISeriesApi<'Histogram'> | null = null;
    if (showVolume) {
      volSeries = chart.addHistogramSeries({
        priceScaleId: 'vol',
        priceFormat: { type: 'volume' },
        color: '#334155',
      });
      chart.priceScale('vol').applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
    }

    let lastBarTime = 0;
    let ws: WebSocket | null = null;

    const loadHistory = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/charts/${symbol}/candles?timeframe=${timeframe}&limit=500`,
          { headers: authHeaders() }
        );
        const data = await res.json();
        const candles: any[] = data.candles || [];
        const sorted = [...candles].sort(
          (a, b) => Number(a.time ?? Date.parse(a.timestamp)) - Number(b.time ?? Date.parse(b.timestamp))
        );

        if (chartType === 'line' || chartType === 'area') {
          const lineData: LineData[] = sorted.map((c) => ({
            time: toTime(Number(c.time ?? Math.floor(Date.parse(c.timestamp) / 1000))),
            value: Number(c.close),
          }));
          series.setData(lineData as any);
        } else {
          const candleData: CandlestickData[] = sorted.map((c) => ({
            time: toTime(Number(c.time ?? Math.floor(Date.parse(c.timestamp) / 1000))),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
          }));
          series.setData(candleData as any);
        }

        if (volSeries) {
          const volData: HistogramData[] = sorted.map((c) => ({
            time: toTime(Number(c.time ?? Math.floor(Date.parse(c.timestamp) / 1000))),
            value: Number(c.volume || 0),
            color: Number(c.close) >= Number(c.open) ? '#16a34a80' : '#dc262480',
          }));
          volSeries.setData(volData as any);
        }

        if (sorted.length > 0) {
          lastBarTime = Number(sorted[sorted.length - 1].time ?? Math.floor(Date.parse(sorted[sorted.length - 1].timestamp) / 1000));
        }
        chart.timeScale().fitContent();

        if (showMA || showEMA || showRSI) loadIndicators();
        if (showStrength) loadStrength();
        if (plan) drawPlan(plan);
      } catch (e) {
        console.error('Failed to load history', e);
      }
    };

    const loadIndicators = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/charts/${symbol}/indicators?timeframe=${timeframe}&limit=500`,
          { headers: authHeaders() }
        );
        const data = await res.json();
        const times: number[] = data.times || [];
        if (!times.length) return;

        if (showMA) {
          if (data.sma20 && data.sma20.some((v: any) => v != null)) {
            const s = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            s.setData(times.map((t, i) => ({ time: toTime(t), value: data.sma20[i] })).filter((d: any) => d.value != null) as any);
          }
          if (data.sma50 && data.sma50.some((v: any) => v != null)) {
            const s = chart.addLineSeries({ color: '#a855f7', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            s.setData(times.map((t, i) => ({ time: toTime(t), value: data.sma50[i] })).filter((d: any) => d.value != null) as any);
          }
        }
        if (showEMA && data.ema20 && data.ema20.some((v: any) => v != null)) {
          const s = chart.addLineSeries({ color: '#22d3ee', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
          s.setData(times.map((t, i) => ({ time: toTime(t), value: data.ema20[i] })).filter((d: any) => d.value != null) as any);
        }
        if (showRSI) mountRsi(times, data.rsi14 || []);
      } catch (e) {
        console.error('Failed to load indicators', e);
      }
    };

    const loadStrength = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/charts/${symbol}/strength?timeframe=${timeframe}`, { headers: authHeaders() });
        const data = await res.json();
        const times: number[] = data.times || [];
        if (!times.length) return;
        if (data.adx_series && data.adx_series.some((v: any) => v != null)) {
          mountStrength(times, data.adx_series, data.strength_series || []);
        }
      } catch (e) {
        console.error('Failed to load strength', e);
      }
    };

    const drawPlan = (p: Plan) => {
      if (!p || p.entry == null) return;
      const addLine = (price: number | null, color: string, title: string) => {
        if (price == null) return;
        try {
          series.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2 as any, axisLabelVisible: true, title });
        } catch {
          /* ignore */
        }
      };
      addLine(p.entry, '#3b82f6', 'Entry');
      addLine(p.stop_loss, '#ef4444', 'SL');
      addLine(p.take_profit, '#22c55e', 'TP');
      if (p.support != null) addLine(p.support, '#16a34a', 'Support');
      if (p.resistance != null) addLine(p.resistance, '#dc2626', 'Resistance');

      if (p.forecast && p.forecast.length) {
        try {
          const fc = chart.addLineSeries({
            color: '#f59e0b',
            lineWidth: 2,
            lineStyle: 2 as any,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          fc.setData(
            p.forecast.map((d) => ({ time: toTime(d.time), value: d.value })) as any
          );
        } catch {
          /* ignore */
        }
      }
    };

    const mountRsi = (times: number[], rsi: (number | null)[]) => {
      const rsiContainer = rsiContainerRef.current;
      if (!rsiContainer) return;
      const rsiChart = createChart(rsiContainer, {
        width: rsiContainer.clientWidth,
        height: rsiContainer.clientHeight,
        layout: {
          background: { type: ColorType.Solid, color: '#0a0e1a' },
          textColor: '#94a3b8',
          fontSize: 10,
        },
        grid: {
          vertLines: { color: '#1e2433' },
          horzLines: { color: '#1e2433' },
        },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 } },
      });
      const rsiSeries = rsiChart.addLineSeries({ color: '#eab308', lineWidth: 1, priceLineVisible: false });
      rsiSeries.setData(
        times
          .map((t, i) => ({ time: toTime(t), value: rsi[i] }))
          .filter((d: any) => d.value != null) as any
      );
      rsiSeries.createPriceLine({ price: 70, color: '#ef4444', lineWidth: 1, lineStyle: 2 as any, axisLabelVisible: true, title: '70' });
      rsiSeries.createPriceLine({ price: 30, color: '#22c55e', lineWidth: 1, lineStyle: 2 as any, axisLabelVisible: true, title: '30' });
      rsiChart.timeScale().fitContent();
      rsiChartRef.current = rsiChart;
      rsiSeriesRef.current = rsiSeries;

      const syncRange = (range: any) => {
        if (range && rsiChartRef.current) {
          rsiChartRef.current.timeScale().setVisibleLogicalRange(range);
        }
      };
      chart.timeScale().subscribeVisibleLogicalRangeChange(syncRange);
      rsiRangeUnsubRef.current = () => {
        try {
          chart.timeScale().unsubscribeVisibleLogicalRangeChange(syncRange);
        } catch {
          /* noop */
        }
      };
    };

    const mountStrength = (times: number[], adx: (number | null)[], strength: (number | null)[]) => {
      const el = strengthContainerRef.current;
      if (!el) return;
      const sc = createChart(el, {
        width: el.clientWidth,
        height: el.clientHeight,
        layout: {
          background: { type: ColorType.Solid, color: '#0a0e1a' },
          textColor: '#94a3b8',
          fontSize: 10,
        },
        grid: {
          vertLines: { color: '#1e2433' },
          horzLines: { color: '#1e2433' },
        },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 } },
      });
      const adxSeries = sc.addLineSeries({ color: '#60a5fa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      adxSeries.setData(
        times.map((t, i) => ({ time: toTime(t), value: adx[i] })).filter((d: any) => d.value != null) as any
      );
      if (strength && strength.length) {
        const ss = sc.addLineSeries({ color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        ss.setData(
          times.map((t, i) => ({ time: toTime(t), value: strength[i] })).filter((d: any) => d.value != null) as any
        );
      }
      adxSeries.createPriceLine({ price: 25, color: '#ef4444', lineWidth: 1, lineStyle: 2 as any, axisLabelVisible: true, title: 'ADX25' });
      adxSeries.createPriceLine({ price: 50, color: '#64748b', lineWidth: 1, lineStyle: 2 as any, axisLabelVisible: true, title: '50' });
      sc.timeScale().fitContent();
      strengthChartRef.current = sc;
      strengthSeriesRef.current = adxSeries;

      const syncRange = (range: any) => {
        if (range && strengthChartRef.current) {
          strengthChartRef.current.timeScale().setVisibleLogicalRange(range);
        }
      };
      chart.timeScale().subscribeVisibleLogicalRangeChange(syncRange);
      strengthRangeUnsubRef.current = () => {
        try {
          chart.timeScale().unsubscribeVisibleLogicalRangeChange(syncRange);
        } catch {
          /* noop */
        }
      };
    };

    loadHistory();

    try {
      ws = new WebSocket(wsUrl(`${WS_URL}/api/v1/ws/chart/${symbol}?timeframe=${timeframe}`));
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'tick' && msg.tick) {
            const t = msg.tick;
            let time = Math.floor((t.timestamp || Date.now()) / 1000) as number;
            if (time < lastBarTime) time = lastBarTime;
            lastBarTime = time;

            if (chartType === 'line' || chartType === 'area') {
              series.update({ time: time as Time, value: Number(t.price) } as any);
            } else {
              series.update({
                time: time as Time,
                open: Number(t.price),
                high: Number(t.price),
                low: Number(t.price),
                close: Number(t.price),
              } as any);
            }
          }
        } catch {
          /* ignore malformed messages */
        }
      };
    } catch (e) {
      console.error('WebSocket connection failed', e);
    }

    // Auto-resize (handles fullscreen toggles + sidebar/container changes).
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
      }
      if (rsiContainerRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({ width: rsiContainerRef.current.clientWidth });
      }
      if (strengthContainerRef.current && strengthChartRef.current) {
        strengthChartRef.current.applyOptions({ width: strengthContainerRef.current.clientWidth });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (ws) ws.close();
      if (rsiRangeUnsubRef.current) rsiRangeUnsubRef.current();
      if (strengthRangeUnsubRef.current) strengthRangeUnsubRef.current();
      chart.remove();
      if (rsiChartRef.current) rsiChartRef.current.remove();
      if (strengthChartRef.current) strengthChartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = null;
      rsiChartRef.current = null;
      rsiSeriesRef.current = null;
      rsiRangeUnsubRef.current = null;
      strengthChartRef.current = null;
      strengthSeriesRef.current = null;
      strengthRangeUnsubRef.current = null;
    };
  }, [symbol, timeframe, chartType, showMA, showEMA, showRSI, showVolume, showStrength, plan]);

  return (
    <div className="flex flex-col h-full gap-2">
      <div
        id="trading-chart-container"
        ref={containerRef}
        className="w-full flex-1 min-h-0 rounded-lg overflow-hidden border border-[#1e2433] bg-[#0d1117]"
      />
      {showRSI && (
        <div
          ref={rsiContainerRef}
          className="w-full h-[150px] shrink-0 rounded-lg overflow-hidden border border-[#1e2433] bg-[#0d1117]"
        />
      )}
      {showStrength && (
        <div
          ref={strengthContainerRef}
          className="w-full h-[150px] shrink-0 rounded-lg overflow-hidden border border-[#1e2433] bg-[#0d1117]"
        />
      )}
    </div>
  );
}
