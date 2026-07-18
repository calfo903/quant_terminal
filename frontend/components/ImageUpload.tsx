'use client';



import { useState } from 'react';
import { authHeaders } from '../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';



export default function ImageUpload({

  onAnalysisComplete,

  onClose,

}: {

  onAnalysisComplete: (result: any) => void;

  onClose: () => void;

}) {

  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);



  const handleUpload = async () => {

    if (!file) return;

    setLoading(true);

    setError(null);

    try {

      const fd = new FormData();

      fd.append('file', file);

      const res = await fetch(`${API_URL}/api/v1/image/analyze`, {
        method: 'POST',
        headers: authHeaders(),
        body: fd,
      });

      if (!res.ok) throw new Error(`Upload failed (${res.status})`);

      const result = await res.json();

      onAnalysisComplete(result);

    } catch (e: any) {

      setError(e?.message || 'Analysis failed');

    } finally {

      setLoading(false);

    }

  };



  return (

    <div

      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"

      onClick={onClose}

    >

      <div

        className="bg-[#161b22] border border-[#1e2433] rounded-xl p-6 w-[420px]"

        onClick={(e) => e.stopPropagation()}

      >

        <h2 className="text-lg font-semibold mb-4">Upload Chart Image</h2>

        <input

          type="file"

          accept="image/*"

          onChange={(e) => setFile(e.target.files?.[0] ?? null)}

          className="mb-4 text-sm text-gray-300"

        />

        {error && <p className="text-red-400 text-sm mb-2">{error}</p>}

        <div className="flex justify-end space-x-2">

          <button

            onClick={onClose}

            className="px-4 py-2 rounded text-sm text-gray-300 hover:text-white"

          >

            Cancel

          </button>

          <button

            onClick={handleUpload}

            disabled={!file || loading}

            className="px-4 py-2 rounded text-sm bg-purple-600 hover:bg-purple-700 disabled:opacity-50"

          >

            {loading ? 'Analyzing…' : 'Analyze'}

          </button>

        </div>

      </div>

    </div>

  );

}
