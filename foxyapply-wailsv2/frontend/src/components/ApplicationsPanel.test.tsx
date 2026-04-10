import { describe, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { ApplicationsPanel } from './ApplicationsPanel'

describe('ApplicationsPanel', () => {
  const defaultProps = {
    selectedProfile: 1,
    browserRunning: true,
    viewMode: 'wizard' as 'wizard' | 'dashboard' | 'settings',
    setViewMode: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders placeholder when no profile is selected', () => {
    render(<ApplicationsPanel {...defaultProps} selectedProfile={null} />)
  })

  // it('renders all sections when browser is running and profile is selected', () => {
  //   render(<ApplicationsPanel {...defaultProps} />)

  //   expect(screen.getByText('Navigation')).toBeInTheDocument()
  //   expect(screen.getByText('Element Actions')).toBeInTheDocument()
  //   expect(screen.getByText('JavaScript')).toBeInTheDocument()
  //   expect(screen.getByText('Screenshot')).toBeInTheDocument()
  // })

  // it('calls onNavigate with https prefix when URL lacks protocol', async () => {
  //   const user = userEvent.setup()
  //   const onNavigate = vi.fn()
  //   render(<ApplicationsPanel {...defaultProps} onNavigate={onNavigate} />)
  // })

  // it('calls onNavigate with original URL when it has http prefix', async () => {
  //   const user = userEvent.setup()
  //   const onNavigate = vi.fn()
  //   render(<ApplicationsPanel {...defaultProps} onNavigate={onNavigate} />)

  //   const urlInput = screen.getByPlaceholderText('Enter URL...')
  //   await user.type(urlInput, 'http://example.com')

  //   const goButton = screen.getByRole('button', { name: 'Go' })
  //   await user.click(goButton)

  //   expect(onNavigate).toHaveBeenCalledWith('http://example.com')
  // })

  // it('navigates on Enter key press', async () => {
  //   const user = userEvent.setup()
  //   const onNavigate = vi.fn()
  //   render(<ApplicationsPanel {...defaultProps} onNavigate={onNavigate} />)

  //   const urlInput = screen.getByPlaceholderText('Enter URL...')
  //   await user.type(urlInput, 'example.com{Enter}')

  //   expect(onNavigate).toHaveBeenCalledWith('https://example.com')
  // })

  // it('calls Click handler with selector', async () => {
  //   const user = userEvent.setup()
  //   const mockClick = vi.fn().mockResolvedValue(undefined)
  //   App.Click = mockClick

  //   render(<AutomationPanel {...defaultProps} />)

  //   const selectorInput = screen.getByPlaceholderText(/CSS Selector/)
  //   await user.type(selectorInput, '#submit-btn')

  //   const clickButton = screen.getByRole('button', { name: 'Click' })
  //   await user.click(clickButton)

  //   expect(mockClick).toHaveBeenCalledWith('page-1', '#submit-btn')
  // })

  // it('displays error message when action fails', async () => {
  //   const user = userEvent.setup()
  //   const mockClick = vi.fn().mockRejectedValue(new Error('Element not found'))
  //   App.Click = mockClick

  //   render(<AutomationPanel {...defaultProps} />)

  //   const selectorInput = screen.getByPlaceholderText(/CSS Selector/)
  //   await user.type(selectorInput, '#nonexistent')

  //   const clickButton = screen.getByRole('button', { name: 'Click' })
  //   await user.click(clickButton)

  //   expect(await screen.findByText(/Error:/)).toBeInTheDocument()
  // })
})
