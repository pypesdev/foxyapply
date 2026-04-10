import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock Wails runtime
vi.mock('../lib/wailsjs/runtime/runtime', () => ({
  EventsOn: vi.fn(),
  EventsOff: vi.fn(),
  EventsEmit: vi.fn(),
}))

// Mock window.go (Wails bindings)
Object.defineProperty(window, 'go', {
  value: {
    app: {
      App: {
        // Browser methods
        StartBrowser: vi.fn(),
        StopBrowser: vi.fn(),
        Navigate: vi.fn(),
        Click: vi.fn(),
        Type: vi.fn(),
        Screenshot: vi.fn(),
        Eval: vi.fn(),
        GetText: vi.fn(),
        NewPage: vi.fn(),
        ClosePage: vi.fn(),
        GetPages: vi.fn(),
        // Store methods (persistence)
        CreateNote: vi.fn(),
        GetNote: vi.fn(),
        ListNotes: vi.fn(),
        UpdateNote: vi.fn(),
        DeleteNote: vi.fn(),
        GetSetting: vi.fn(),
        SetSetting: vi.fn(),
        GetAllSettings: vi.fn(),
      },
    },
  },
  writable: true,
})
