import { useState, useEffect, useCallback } from 'react'
import { BrowserControls } from './components/BrowserControls'
import { ProfileList } from './components/ProfileList'
import { StatusBar } from './components/StatusBar'
import {
  DownloadBrowser,
  GetBrowserStatus,
  ListLinkedInProfiles,
  SetApplying,
  StartApplying,
  StopBrowser,
} from '../bindings/foxyapply/appservice'
import { BrowserStatus } from '../bindings/foxyapply/index'
import { LinkedInProfile } from '../bindings/foxyapply/internal/store'
import { ApplicationsPanel } from './components/ApplicationsPanel'
import { Events } from '@wailsio/runtime'
export interface PageInfo {
  id: string
  url: string
  title: string
}

export interface ActionResult {
  success: boolean
  data?: unknown
  error?: string
}

function App() {
  const [status, setStatus] = useState<BrowserStatus | null>(null)
  const [profiles, setProfiles] = useState<LinkedInProfile[]>([])
  const [selectedProfile, setSelectedProfile] = useState<number | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'wizard' | 'dashboard' | 'settings'>('wizard')

  const refreshStatus = useCallback(async () => {
    try {
      const s = await GetBrowserStatus()
      setStatus(s)
    } catch (e) {
      console.error('Failed to get status:', e)
    }
  }, [])

  const refreshProfiles = useCallback(async () => {
    try {
      const p = await ListLinkedInProfiles()
      if (p) {
        setProfiles(p.filter((profile): profile is LinkedInProfile => profile !== null))
        if (selectedProfile === null && p.length > 0) {
          setSelectedProfile(p[0]!.id)
        }
      }
    } catch (e) {
      console.error('Failed to get profiles:', e)
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    // Listen for browser events
    const unsubStart = Events.On('browser:started', () => {
      refreshStatus()
      refreshProfiles()
    })

    const unsubStop = Events.On('browser:stopped', () => {
      refreshStatus()
    })

    const unsubProgress = Events.On('browser:download-progress', (ev) => {
      const progress = ev.data as { percent: number }
      setDownloadProgress(progress.percent)
    })

    const unsubDownloaded = Events.On('browser:downloaded', () => {
      setDownloading(false)
      setDownloadProgress(100)
      refreshStatus()
    })

    return () => {
      unsubStart()
      unsubStop()
      unsubProgress()
      unsubDownloaded()
    }
  }, [refreshStatus, refreshProfiles])

  useEffect(() => {
    refreshProfiles()
  }, [refreshProfiles])

  const handleStartApplying = async () => {
    try {
      setError(null)
      if (selectedProfile === null) {
        setError('Please select a LinkedIn profile to start applying.')
        return
      }
      await SetApplying(true)
      await refreshStatus()
      await StartApplying(selectedProfile)
    } catch (e) {
      setError(`Failed to start applying: ${e}`)
    }
  }

  const handleStopBrowser = async () => {
    try {
      setError(null)
      await StopBrowser()
    } catch (e) {
      setError(`Failed to stop browser: ${e}`)
    }
  }

  const handleDownloadBrowser = async () => {
    try {
      setError(null)
      setDownloading(true)
      setDownloadProgress(0)
      await DownloadBrowser()
      await refreshStatus()
    } catch (e) {
      setError(`Failed to download browser: ${e}`)
      setDownloading(false)
    }
  }

  const handleProfileCreated = (profile: LinkedInProfile) => {
    setProfiles((prev) => [...prev, profile])
    setSelectedProfile(profile.id)
  }

  const handleProfileDeleted = (profileID: number) => {
    setProfiles((prev) => prev.filter((p) => p.id !== profileID))
    if (selectedProfile === profileID) {
      setSelectedProfile(null)
    }
  }

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Apply Fox</h1>
        <span style={styles.subtitle}>Automate your job applications</span>
      </header>

      {error && (
        <div style={styles.error}>
          {error}
          <button onClick={() => setError(null)} style={styles.dismissBtn}>
            ×
          </button>
        </div>
      )}

      <div style={styles.main}>
        <aside style={styles.sidebar}>
          <BrowserControls
            status={status}
            downloading={downloading}
            downloadProgress={downloadProgress}
            onStart={handleStartApplying}
            onStop={handleStopBrowser}
            onDownload={handleDownloadBrowser}
            selectedProfile={selectedProfile}
            viewMode={viewMode}
          />

          <ProfileList
            profiles={profiles}
            selectedProfile={selectedProfile}
            onSelect={setSelectedProfile}
            onProfileCreated={handleProfileCreated}
            onProfileDeleted={handleProfileDeleted}
            refreshProfiles={refreshProfiles}
            status={status}
          />
        </aside>

        <main style={styles.content}>
          <ApplicationsPanel
            selectedProfile={selectedProfile}
            setViewMode={setViewMode}
            viewMode={viewMode}
          />
        </main>
      </div>

      <StatusBar status={status} profileCount={profiles.length} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    width: '100vw'
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '32px 24px 8px 24px',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },
  title: {
    fontSize: '20px',
    fontWeight: 600,
    color: '#fff',
  },
  subtitle: {
    fontSize: '14px',
    color: '#888',
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 24px',
    background: '#ff4757',
    color: '#fff',
  },
  dismissBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    fontSize: '20px',
    cursor: 'pointer',
  },
  main: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  sidebar: {
    width: '280px',
    borderRight: '1px solid rgba(255,255,255,0.1)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'auto',
  },
  content: {
    flex: 1,
    overflow: 'auto',
    padding: '24px',
  },
}

export default App
