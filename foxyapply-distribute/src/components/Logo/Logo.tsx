import clsx from 'clsx'
import React from 'react'

interface Props {
  className?: string
}

export const Logo = (props: Props) => {
  const { className } = props

  return (
    <div
      className={clsx('flex items-center gap-2', className)}
    >
      <svg
        width="40"
        height="40"
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0"
      >
        <circle cx="20" cy="20" r="20" fill="#F97316" />
        <ellipse cx="14" cy="16" rx="3" ry="4" fill="white" />
        <ellipse cx="26" cy="16" rx="3" ry="4" fill="white" />
        <circle cx="14" cy="17" r="1.5" fill="#1F2937" />
        <circle cx="26" cy="17" r="1.5" fill="#1F2937" />
        <path
          d="M12 26C12 26 15 30 20 30C25 30 28 26 28 26"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M6 12C6 12 8 8 12 10"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M34 12C34 12 32 8 28 10"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <span className="font-bold text-xl tracking-tight">ApplyFox</span>
    </div>
  )
}
