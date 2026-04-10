import type { Metadata } from 'next'
import { LandingPage } from '@/components/LandingPage'

export default function Home() {
  return <LandingPage />
}

export const metadata: Metadata = {
  title: 'ApplyFox - Auto-Apply to Jobs on LinkedIn | Land Your Six-Figure Job',
  description:
    'ApplyFox automatically applies to jobs on LinkedIn while you sleep. Set your preferences and let our AI-powered desktop app do the heavy lifting. 10x your applications with zero extra effort.',
  openGraph: {
    title: 'ApplyFox - Auto-Apply to Jobs on LinkedIn',
    description:
      'Land your six-figure job on autopilot. ApplyFox automatically applies to jobs on LinkedIn while you sleep.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ApplyFox - Auto-Apply to Jobs on LinkedIn',
    description:
      'Land your six-figure job on autopilot. ApplyFox automatically applies to jobs on LinkedIn while you sleep.',
  },
}
