import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ClawChain - Mine with Your AI Agent',
  description: 'The first Proof of Availability blockchain. OpenClaw agents mine $CLAW automatically while idle.',
  keywords: 'ClawChain,AI,Agent,mining,blockchain,Proof of Availability,$CLAW,OpenClaw',
  openGraph: {
    title: 'ClawChain - Mine with Your AI Agent',
    description: 'The first Proof of Availability blockchain. OpenClaw agents mine $CLAW automatically while idle.',
    type: 'website',
    url: 'https://0xverybigorange.github.io/clawchain/',
    siteName: 'ClawChain',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ClawChain - Mine with Your AI Agent',
    description: 'First Proof of Availability blockchain. OpenClaw agents mine $CLAW automatically.',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  )
}
