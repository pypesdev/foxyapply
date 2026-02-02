import { BrowserStatus } from '../../bindings/foxyapply'

interface StatusBarProps {
  status: BrowserStatus | null
  profileCount: number
}

export function StatusBar({ status, profileCount }: StatusBarProps) {
  const isRunning = status?.running ?? false

  return (
    <footer style={styles.container}>
      <div style={styles.left}>
        <span style={getIndicatorStyle(isRunning)} />
        <span style={styles.text}>{isRunning ? 'Browser Running' : 'Browser Stopped'}</span>
      </div>
      <div style={styles.right}>
        <span style={styles.text}>{profileCount} profile(s)</span>
        {status?.version && <span style={styles.version}>Chrome {status.version}</span>}
      </div>
    </footer>
  )
}

const getIndicatorStyle = (running: boolean): React.CSSProperties => ({
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  background: running ? '#00b894' : '#888',
})

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    background: 'rgba(0,0,0,0.2)',
    borderTop: '1px solid rgba(255,255,255,0.1)',
    fontSize: '12px',
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  text: {
    color: '#888',
  },
  version: {
    color: '#666',
    fontFamily: 'monospace',
  },
}
