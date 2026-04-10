'use client'

import React from 'react'

const testimonials = [
  {
    quote: "I was spending hours every day applying to jobs. ApplyFox let me apply to 50+ positions per day while I focused on interview prep. Landed a $140K offer in 2 weeks.",
    author: "Sarah K.",
    role: "Senior Software Engineer",
    company: "Now at Google",
  },
  {
    quote: "The LinkedIn integration is seamless. I set my preferences once and ApplyFox handled everything. Went from 0 interviews to 5 in my first week.",
    author: "Marcus T.",
    role: "Product Manager",
    company: "Now at Stripe",
  },
  {
    quote: "As a career changer, I needed to cast a wide net. ApplyFox helped me apply to 200+ roles in my target field. Got my dream job at a startup paying $120K.",
    author: "Jennifer L.",
    role: "Data Analyst",
    company: "Now at Airbnb",
  },
]

export const Testimonials: React.FC = () => {
  return (
    <section className="py-24 bg-background">
      <div className="container">
        {/* Section header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="inline-block text-orange-500 font-semibold text-sm uppercase tracking-wider mb-4">
            Success Stories
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Join thousands who landed their dream jobs
          </h2>
          <p className="text-lg text-muted-foreground">
            Real results from real job seekers who used ApplyFox to accelerate their job search.
          </p>
        </div>

        {/* Testimonials grid */}
        <div className="grid md:grid-cols-3 gap-8">
          {testimonials.map((testimonial, index) => (
            <div
              key={index}
              className="relative bg-card border border-border rounded-xl p-8 hover:shadow-lg transition-shadow"
            >
              {/* Quote icon */}
              <div className="absolute -top-4 left-8">
                <div className="w-8 h-8 rounded-full bg-orange-500 flex items-center justify-center">
                  <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z" />
                  </svg>
                </div>
              </div>

              {/* Quote */}
              <blockquote className="text-foreground leading-relaxed mb-6 pt-4">
                &ldquo;{testimonial.quote}&rdquo;
              </blockquote>

              {/* Author */}
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white font-semibold">
                  {testimonial.author.split(' ').map(n => n[0]).join('')}
                </div>
                <div>
                  <div className="font-semibold text-foreground">{testimonial.author}</div>
                  <div className="text-sm text-muted-foreground">{testimonial.role}</div>
                  <div className="text-sm text-orange-500">{testimonial.company}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
