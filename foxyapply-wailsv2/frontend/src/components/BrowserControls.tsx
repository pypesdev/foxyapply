import { app } from '../lib/wailsjs/go/models'

interface BrowserControlsProps {
  status: app.BrowserStatus | null
  downloading: boolean
  downloadProgress: number
  onStart: () => void
  onStop: () => void
  onDownload: () => void
  selectedProfile: number | null
  viewMode?: 'wizard' | 'dashboard' | 'settings'
}

export function BrowserControls({
  status,
  downloading,
  downloadProgress,
  onStart,
  onStop,
  onDownload,
  selectedProfile,
  viewMode,
}: BrowserControlsProps) {
  const isOnboarding = () => {
    if (viewMode === 'wizard') {
      return true
    }
    if (selectedProfile === null) {
      return true
    }
    return false
  }
  const isRunning = status?.running ?? false
  const isDownloaded = status?.downloaded ?? false
  const hasCompletedOnboarding = isOnboarding()

  const promptToContinue = isDownloaded ? 'Add a Profile to Start' : 'Download Browser to Start'
  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>Browser</h3>

      {!isDownloaded && (
        <div style={styles.section}>
          <p style={styles.info}>Chrome for Testing not found</p>
          <button style={styles.downloadBtn} onClick={onDownload} disabled={downloading}>
            {downloading ? `Downloading... ${downloadProgress.toFixed(0)}%` : 'Download Browser'}
          </button>
          {downloading && (
            <div style={styles.progressBar}>
              <div
                style={{
                  ...styles.progressFill,
                  width: `${downloadProgress}%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      <div style={styles.buttonGroup}>
        {!status?.applying ? (
          <button
            style={{
              ...styles.startBtn,
              ...(hasCompletedOnboarding ? styles.startBtnDisabled : {}),
            }}
            onClick={() => onStart()}
            disabled={!isDownloaded || hasCompletedOnboarding}
          >
            {hasCompletedOnboarding ? promptToContinue : 'Start Applying'}
          </button>
        ) : (
          <button style={styles.stopBtn} onClick={onStop}>
            Stop Browser
          </button>
        )}
      </div>

      <div style={styles.statusInfo}>
        <div style={styles.statusRow}>
          <span>Status</span>
          <span style={isRunning ? styles.statusOn : styles.statusOff}>
            {isRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
        {status?.version && (
          <div style={styles.statusRow}>
            <span>Version</span>
            <span style={styles.version}>{status.version}</span>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '16px',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },
  heading: {
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: '#888',
    marginBottom: '12px',
  },
  section: {
    marginBottom: '16px',
  },
  info: {
    fontSize: '13px',
    color: '#888',
    marginBottom: '8px',
  },
  downloadBtn: {
    width: '100%',
    padding: '10px',
    background: '#cf5200',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 500,
  },
  progressBar: {
    height: '4px',
    background: 'rgba(255,255,255,0.1)',
    borderRadius: '2px',
    marginTop: '8px',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    background: '#0984e3',
    transition: 'width 0.3s',
  },
  checkbox: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '14px',
    color: '#ccc',
    cursor: 'pointer',
  },
  buttonGroup: {
    marginBottom: '16px',
  },
  startBtn: {
    width: '100%',
    padding: '12px',
    background: '#cf5200',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 600,
  },
  startBtnDisabled: {
    background: '#555',
    color: '#888',
    cursor: 'not-allowed',
  },
  stopBtn: {
    width: '100%',
    padding: '12px',
    background: '#cf5200',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 600,
  },
  statusInfo: {
    fontSize: '13px',
  },
  statusRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '6px 0',
    color: '#888',
  },
  statusOn: {
    color: '#00b894',
    fontWeight: 500,
  },
  statusOff: {
    color: '#888',
  },
  version: {
    color: '#ddd',
    fontFamily: 'monospace',
    fontSize: '12px',
  },
}
