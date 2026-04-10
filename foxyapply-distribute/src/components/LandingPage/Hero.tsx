'use client'

import React from 'react'
import { useHeaderTheme } from '@/providers/HeaderTheme'
import { useEffect } from 'react'
import { DownloadButton } from './DownloadButton'

export const Hero: React.FC = () => {
  const { setHeaderTheme } = useHeaderTheme()

  useEffect(() => {
    setHeaderTheme('dark')
  }, [setHeaderTheme])

  return (
    <section
      className="relative -mt-[10.4rem] min-h-[90vh] flex items-center justify-center overflow-hidden"
      data-theme="dark"
    >
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-orange-600 via-orange-500 to-amber-500" />

      {/* Animated background shapes */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-white/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-orange-300/20 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-gradient-radial from-white/5 to-transparent rounded-full" />
      </div>

      {/* Content */}
      <div className="container relative z-10 text-center text-white pt-32 pb-20">
        <div className="max-w-4xl mx-auto">
          {/* App Icon */}
          <div className="mb-6">
            <img
              src="/appicon.png"
              alt="ApplyFox"
              className="w-20 h-20 md:w-24 md:h-24 mx-auto rounded-2xl shadow-2xl"
            />
          </div>

          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full px-4 py-2 mb-8">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400"></span>
            </span>
            <span className="text-sm font-medium">Now with LinkedIn auto-apply</span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-6">
            Land Your Six-Figure Job
            <span className="block text-white/90">On Autopilot</span>
          </h1>

          {/* Subheadline */}
          <p className="text-lg md:text-xl text-white/80 max-w-2xl mx-auto mb-10 leading-relaxed">
            ApplyFox automatically applies to jobs on LinkedIn while you sleep.
            Set your preferences, and let our AI-powered desktop app do the heavy lifting.
            <span className="font-semibold text-white"> 10x your applications. Zero extra effort.</span>
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12">
            <DownloadButton />
            <a
              href="#features"
              className="inline-flex items-center gap-2 px-6 py-3 text-white/90 hover:text-white transition-colors font-medium"
            >
              See how it works
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </a>
          </div>

          {/* Social proof */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 text-sm text-white/70 mb-12">
            <div className="flex items-center gap-2">
              <div className="flex -space-x-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div
                    key={i}
                    className="w-8 h-8 rounded-full bg-gradient-to-br from-gray-200 to-gray-400 border-2 border-orange-500"
                  />
                ))}
              </div>
              <span>10,000+ job seekers</span>
            </div>
            <div className="hidden sm:block w-px h-4 bg-white/30" />
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 5].map((i) => (
                <svg key={i} className="w-4 h-4 text-yellow-300 fill-current" viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
              ))}
              <span className="ml-1">4.9/5 rating</span>
            </div>
          </div>

          {/* Demo Video */}
          <div className="relative max-w-4xl mx-auto">
            <div className="relative rounded-xl overflow-hidden shadow-2xl border border-white/20 bg-black/20 backdrop-blur-sm">
              <video
                className="w-full"
                autoPlay
                loop
                muted
                playsInline
                poster="/appicon.png"
              >
                <source src="/demo.mp4" type="video/mp4" />
                Your browser does not support the video tag.
              </video>
            </div>
            {/* Video glow effect */}
            <div className="absolute -inset-4 bg-gradient-to-r from-orange-400/20 via-amber-400/20 to-orange-400/20 rounded-2xl blur-2xl -z-10" />
          </div>
        </div>
      </div>

      {/* Bottom wave */}
      <div className="absolute bottom-0 left-0 right-0">
        <svg viewBox="0 0 1440 120" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
          <path
            d="M0 120L60 110C120 100 240 80 360 70C480 60 600 60 720 65C840 70 960 80 1080 85C1200 90 1320 90 1380 90L1440 90V120H1380C1320 120 1200 120 1080 120C960 120 840 120 720 120C600 120 480 120 360 120C240 120 120 120 60 120H0Z"
            className="fill-background"
          />
        </svg>
      </div>
    </section>
  )
}
