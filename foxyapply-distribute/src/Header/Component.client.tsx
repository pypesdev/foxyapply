'use client'
import { useHeaderTheme } from '@/providers/HeaderTheme'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import React, { useEffect, useState } from 'react'

import { Logo } from '@/components/Logo/Logo'

export const HeaderClient: React.FC = () => {
  const [theme, setTheme] = useState<string | null>(null)
  const { headerTheme, setHeaderTheme } = useHeaderTheme()
  const pathname = usePathname()

  useEffect(() => {
    setHeaderTheme(null)
  }, [pathname, setHeaderTheme])

  useEffect(() => {
    if (headerTheme && headerTheme !== theme) setTheme(headerTheme)
  }, [headerTheme, theme])

  return (
    <header
      className="container relative z-20"
      {...(theme ? { 'data-theme': theme } : {})}
    >
      <div className="py-6 flex justify-between items-center">
        <Link href="/" className="flex items-center">
          <Logo className={theme === 'dark' ? 'text-white' : 'text-foreground'} />
        </Link>

        <nav className="hidden md:flex items-center gap-8">
          <a
            href="#features"
            className="text-sm font-medium opacity-80 hover:opacity-100 transition-opacity"
          >
            Features
          </a>
          <a
            href="#download"
            className="text-sm font-medium opacity-80 hover:opacity-100 transition-opacity"
          >
            Download
          </a>
          <a
            href="#"
            className="text-sm font-medium opacity-80 hover:opacity-100 transition-opacity"
          >
            Pricing
          </a>
          <a
            href="#"
            className="text-sm font-medium opacity-80 hover:opacity-100 transition-opacity"
          >
            Support
          </a>
        </nav>

        <div className="flex items-center gap-4">
          <a
            href="#download"
            className="hidden sm:inline-flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download
          </a>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 rounded-lg hover:bg-white/10 transition-colors"
            aria-label="Menu"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  )
}
