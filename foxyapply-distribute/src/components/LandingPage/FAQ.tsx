'use client'

import React, { useState } from 'react'

const faqs = [
  {
    question: 'Is ApplyFox safe to use with my LinkedIn account?',
    answer: 'Yes! ApplyFox uses official LinkedIn APIs and OAuth authentication. We never store your password, and you can revoke access at any time. Your account security is our top priority.',
  },
  {
    question: 'How many jobs can I apply to per day?',
    answer: 'With ApplyFox, you can apply to up to 100 jobs per day. We intentionally pace applications to mimic human behavior and keep your account in good standing.',
  },
  {
    question: 'Can I customize which jobs ApplyFox applies to?',
    answer: 'Absolutely! You set filters for job title, salary range, location, company size, industry, and more. ApplyFox only applies to positions that match your criteria.',
  },
  {
    question: 'Does ApplyFox work for international job searches?',
    answer: 'Yes! ApplyFox works with LinkedIn globally. You can target jobs in any country or set up location preferences for remote positions.',
  },
  {
    question: 'What happens if a job requires a custom cover letter?',
    answer: 'ApplyFox uses AI to generate tailored cover letters based on your profile and the job description. You can review and customize templates, or skip jobs that require extensive customization.',
  },
  {
    question: 'Is there a free trial?',
    answer: 'Yes! Start with our free tier which includes 20 applications per month. Upgrade anytime to unlock unlimited applications and premium features.',
  },
]

export const FAQ: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <section className="py-24 bg-card">
      <div className="container">
        <div className="max-w-3xl mx-auto">
          {/* Section header */}
          <div className="text-center mb-12">
            <span className="inline-block text-orange-500 font-semibold text-sm uppercase tracking-wider mb-4">
              FAQ
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
              Frequently asked questions
            </h2>
            <p className="text-lg text-muted-foreground">
              Everything you need to know about ApplyFox.
            </p>
          </div>

          {/* FAQ accordion */}
          <div className="space-y-4">
            {faqs.map((faq, index) => (
              <div
                key={index}
                className="border border-border rounded-lg overflow-hidden bg-background"
              >
                <button
                  onClick={() => setOpenIndex(openIndex === index ? null : index)}
                  className="w-full px-6 py-4 text-left flex items-center justify-between gap-4 hover:bg-muted/50 transition-colors"
                >
                  <span className="font-semibold text-foreground">{faq.question}</span>
                  <svg
                    className={`w-5 h-5 text-muted-foreground shrink-0 transition-transform ${
                      openIndex === index ? 'rotate-180' : ''
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {openIndex === index && (
                  <div className="px-6 pb-4">
                    <p className="text-muted-foreground leading-relaxed">{faq.answer}</p>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Contact CTA */}
          <div className="mt-12 text-center">
            <p className="text-muted-foreground mb-4">
              Still have questions? We&apos;re here to help.
            </p>
            <a
              href="mailto:support@applyfox.com"
              className="inline-flex items-center gap-2 text-orange-500 hover:text-orange-600 font-medium"
            >
              Contact support
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
