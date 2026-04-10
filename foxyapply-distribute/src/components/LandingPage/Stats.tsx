'use client'

import React from 'react'

const stats = [
  {
    value: '10,000+',
    label: 'Job Seekers',
    description: 'Trust ApplyFox',
  },
  {
    value: '500K+',
    label: 'Applications',
    description: 'Sent automatically',
  },
  {
    value: '$125K',
    label: 'Average Salary',
    description: 'Of placed users',
  },
  {
    value: '3 weeks',
    label: 'Average Time',
    description: 'To land an offer',
  },
]

export const Stats: React.FC = () => {
  return (
    <section className="py-16 bg-background border-y border-border">
      <div className="container">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 lg:gap-12">
          {stats.map((stat, index) => (
            <div key={index} className="text-center">
              <div className="text-3xl md:text-4xl font-bold text-orange-500 mb-2">
                {stat.value}
              </div>
              <div className="text-lg font-semibold text-foreground mb-1">
                {stat.label}
              </div>
              <div className="text-sm text-muted-foreground">
                {stat.description}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
