'use client'

import React from 'react'
import { DownloadButton } from './DownloadButton'

export const DownloadSection: React.FC = () => {
  return (
    <section id="download" className="py-24 bg-gradient-to-b from-background to-orange-50 dark:to-orange-950/20">
      <div className="container">
        <div className="max-w-4xl mx-auto">
          {/* Main download card */}
          <div className="relative bg-gradient-to-br from-orange-500 to-orange-600 rounded-3xl p-8 md:p-12 overflow-hidden">
            {/* Background decoration */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-orange-300/20 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />

            <div className="relative z-10 text-center text-white">
              <h2 className="text-3xl md:text-4xl font-bold mb-4">
                Ready to land your six-figure job?
              </h2>
              <p className="text-lg text-white/80 mb-8 max-w-2xl mx-auto">
                Download ApplyFox now and start applying to jobs automatically.
                No credit card required. Available for macOS.
              </p>

              <div className="flex flex-col items-center gap-6">
                <DownloadButton variant="hero" />

                <div className="flex flex-wrap items-center justify-center gap-6 text-sm text-white/70">
                  <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-green-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Free to start</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-green-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>No credit card</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-green-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>Cancel anytime</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* macOS download */}
          <div className="mt-12 flex justify-center">
            <a
              href="https://buy.stripe.com/3cI28k3ni1N55o01C42oE0o"
              className="group flex flex-col items-center p-8 bg-card border border-border rounded-xl hover:border-orange-300 hover:shadow-lg transition-all max-w-sm w-full"
            >
              <div className="w-20 h-20 flex items-center justify-center rounded-full bg-gray-100 text-gray-600 mb-4 group-hover:bg-gray-800 group-hover:text-white transition-colors">
                <svg className="w-10 h-10" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
                </svg>
              </div>
              <h3 className="font-semibold text-foreground text-lg mb-1">macOS</h3>
              <p className="text-sm text-muted-foreground mb-3">macOS 11 or later</p>
              <span className="text-sm font-medium text-orange-500 group-hover:text-orange-600">
                Download .zip
              </span>
            </a>
          </div>

          {/* System requirements */}
          <div className="mt-12 text-center">
            <p className="text-sm text-muted-foreground">
              Requires 4GB RAM and 500MB disk space. Internet connection required for job applications.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
