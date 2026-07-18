'use client';

import { useState } from 'react';

export default function AnalysisResults({
  result,
  onImportToChart,
  onClose,
}: {
  result: any;
  onImportToChart: () => void;
  onClose: () => void;
}) {
  if (!result) return null;

  const {
    detected_patterns,
    ocr_text,
    symbol,
    market,
    pair_type,
    sentiment,
    confidence,
    notes,
  } = result;

  const patterns: string[] = detected_patterns || [];
  const noteList: string[] = notes || [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-[#161b22] border border-[#1e2433] rounded-xl p-6 w-[520px] max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Image Analysis</h2>
          {symbol && (
            <span className="text-xs px-2 py-1 bg-blue-600 rounded">{symbol}</span>
          )}
          {market && (
            <span className="text-xs px-2 py-1 bg-slate-700 rounded capitalize">
              {market}
              {pair_type ? ` · ${pair_type}` : ''}
            </span>
          )}
        </div>

        <div className="space-y-3 text-sm">
          <div>
            <span className="text-gray-400">Sentiment: </span>
            <span className="text-white">{sentiment ?? 'n/a'}</span>
          </div>
          <div>
            <span className="text-gray-400">Confidence: </span>
            <span className="text-white">
              {typeof confidence === 'number'
                ? `${(confidence * 100).toFixed(1)}%`
                : confidence}
            </span>
          </div>

          <div>
            <span className="text-gray-400">Patterns:</span>
            <div className="flex flex-wrap gap-2 mt-1">
              {patterns.length === 0 ? (
                <span className="text-gray-500">none detected</span>
              ) : (
                patterns.map((p: string, i: number) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-[#0d1117] border border-[#1e2433] rounded text-xs"
                  >
                    {p}
                  </span>
                ))
              )}
            </div>
          </div>

          {ocr_text && (
            <div>
              <span className="text-gray-400">OCR text:</span>
              <p className="mt-1 whitespace-pre-wrap text-gray-300">{ocr_text}</p>
            </div>
          )}

          {noteList.length > 0 && (
            <div>
              <span className="text-gray-400">Notes:</span>
              <ul className="list-disc ml-5 mt-1 text-gray-300">
                {noteList.map((n: string, i: number) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex justify-end space-x-2 mt-5">
          <button
            onClick={onImportToChart}
            className="px-4 py-2 rounded text-sm bg-blue-600 hover:bg-blue-700"
          >
            Import to Chart
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded text-sm text-gray-300 hover:text-white"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
