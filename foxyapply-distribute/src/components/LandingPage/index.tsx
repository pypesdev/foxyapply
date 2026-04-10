'use client'

import React from 'react'
import { Hero } from './Hero'
import { Stats } from './Stats'
import { Features } from './Features'
import { HowItWorks } from './HowItWorks'
import { Testimonials } from './Testimonials'
import { FAQ } from './FAQ'
import { DownloadSection } from './DownloadSection'

export const LandingPage: React.FC = () => {
  return (
    <>
      <Hero />
      <Stats />
      <Features />
      <HowItWorks />
      <Testimonials />
      <FAQ />
      <DownloadSection />
    </>
  )
}

export { Hero } from './Hero'
export { Stats } from './Stats'
export { Features } from './Features'
export { HowItWorks } from './HowItWorks'
export { Testimonials } from './Testimonials'
export { FAQ } from './FAQ'
export { DownloadSection } from './DownloadSection'
export { DownloadButton } from './DownloadButton'
