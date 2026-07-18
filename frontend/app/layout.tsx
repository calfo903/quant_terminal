import './globals.css';

import type { Metadata } from 'next';

import type { ReactNode } from 'react';



export const metadata: Metadata = {

  title: 'Quant AI Terminal',

  description: 'AI-driven quantitative trading terminal',

};



export default function RootLayout({ children }: { children: ReactNode }) {

  return (

    <html lang="en">

      <body className="bg-[#0a0e1a] text-white antialiased">{children}</body>

    </html>

  );

}
