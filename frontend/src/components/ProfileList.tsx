import { useState } from 'react'
import {
  CreateLinkedInProfile,
  DeleteLinkedInProfile,
  StartBrowser,
} from '../../bindings/foxyapply/appservice'
import { LinkedInProfile } from '../../bindings/foxyapply/internal/store'
import { BrowserStatus } from '../../bindings/foxyapply/index'

interface ProfilePageListProps {
  profiles: LinkedInProfile[]
  selectedProfile: number | null
  onSelect: (profileID: number) => void
  onProfileCreated: (profile: LinkedInProfile) => void
  onProfileDeleted: (profileID: number) => void
  refreshProfiles: () => void
  status: BrowserStatus | null
}

export function ProfileList({
  profiles,
  selectedProfile,
  onSelect,
  onProfileCreated,
  onProfileDeleted,
  refreshProfiles,
  status,
}: ProfilePageListProps) {
  const [showForm, setShowForm] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<LinkedInProfile | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const successfulLogin = await StartBrowser(email, password)
      if (!successfulLogin) {
        throw new Error('Failed to log in')
      }
      const profile = await CreateLinkedInProfile(email, password)
      onProfileCreated(profile!)
      setEmail('')
      setPassword('')
      setShowForm(false)
      refreshProfiles()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create profile'
      setError(`Authentication Failed: ${message}. Please check your credentials and try again.`)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCancel = () => {
    setEmail('')
    setPassword('')
    setError(null)
    setShowForm(false)
  }

  const handleDeleteClick = (e: React.MouseEvent, profile: LinkedInProfile) => {
    e.stopPropagation()
    setDeleteConfirm(profile)
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return
    setIsDeleting(true)

    try {
      await DeleteLinkedInProfile(deleteConfirm.id)
      onProfileDeleted(deleteConfirm.id)
      setDeleteConfirm(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete profile')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleDeleteCancel = () => {
    setDeleteConfirm(null)
  }
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.heading}>LinkedIn Profiles</h3>
      </div>

      {!showForm && (
        <button
          style={{
            ...styles.addProfileBtn,
            ...(!status?.downloaded ? styles.addProfileBtnDisabled : {}),
          }}
          onClick={() => setShowForm(true)}
          disabled={!status?.downloaded}
        >
          {!status?.downloaded ? 'Download Browser to Add Profile' : '+ Add Profile'}
        </button>
      )}

      {showForm && (
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={styles.input}
            required
            autoFocus
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={styles.input}
            required
          />
          {error && <div style={styles.errorBox}>{error}</div>}
          <div style={styles.formButtons}>
            <button
              type="button"
              onClick={handleCancel}
              style={styles.cancelBtn}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button type="submit" style={styles.submitBtn} disabled={isSubmitting}>
              {isSubmitting ? 'Adding...' : 'Add Profile'}
            </button>
          </div>
        </form>
      )}

      {profiles.length === 0 ? (
        <p style={styles.heading}>Add a linkedin profile to get started</p>
      ) : (
        <ul style={styles.list}>
          {profiles.map((profile) => (
            <li
              key={profile.id}
              style={{
                ...styles.item,
                ...(profile.id === selectedProfile ? styles.itemSelected : {}),
              }}
              onClick={() => onSelect(profile.id)}
            >
              <div style={styles.itemContent}>
                <span style={styles.itemTitle}>{profile.email || 'New Tab'}</span>
              </div>
              <button
                style={styles.closeBtn}
                onClick={(e) => handleDeleteClick(e, profile)}
                title="Delete Profile"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {deleteConfirm && (
        <div style={styles.modalOverlay}>
          <div style={styles.modal}>
            <p style={styles.modalText}>Are you sure you want to delete this profile?</p>
            <p style={styles.modalEmail}>{deleteConfirm.email}</p>
            {error && <p style={styles.error}>{error}</p>}
            <div style={styles.formButtons}>
              <button
                type="button"
                onClick={handleDeleteCancel}
                style={styles.cancelBtn}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                style={styles.deleteBtn}
                disabled={isDeleting}
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    padding: '16px',
    overflow: 'auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  heading: {
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: '#888',
  },
  addProfileBtn: {
    width: '100%',
    height: '44px',
    margin: '0 0 12px 0',
    padding: '0 16px',
    background: 'linear-gradient(135deg, #e65c00 0%, #cf5200 100%)',
    border: 'none',
    borderRadius: '8px',
    color: '#fff',
    fontSize: '14px',
    fontWeight: 600,
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 2px 8px rgba(207, 82, 0, 0.3)',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  addProfileBtnDisabled: {
    background: 'rgba(255,255,255,0.08)',
    color: '#666',
    cursor: 'not-allowed',
    boxShadow: 'none',
  },
  empty: {
    fontSize: '13px',
    color: '#666',
    textAlign: 'center',
    padding: '20px',
  },
  list: {
    listStyle: 'none',
    margin: 0,
    padding: 0,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    marginBottom: '4px',
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  itemSelected: {
    background: 'rgba(9, 132, 227, 0.3)',
    boxShadow: 'inset 0 0 0 1px rgba(9, 132, 227, 0.5)',
  },
  itemContent: {
    flex: 1,
    minWidth: 0,
  },
  itemTitle: {
    display: 'block',
    fontSize: '13px',
    fontWeight: 500,
    color: '#eee',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  itemUrl: {
    display: 'block',
    fontSize: '11px',
    color: '#666',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginTop: '2px',
  },
  closeBtn: {
    width: '20px',
    height: '20px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'none',
    border: 'none',
    color: '#888',
    fontSize: '16px',
    cursor: 'pointer',
    opacity: 0.6,
    marginLeft: '8px',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    padding: '12px',
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '6px',
    marginBottom: '12px',
  },
  input: {
    width: '100%',
    height: '38px',
    padding: '0 12px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '13px',
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  formButtons: {
    display: 'flex',
    gap: '8px',
    marginTop: '8px',
  },
  cancelBtn: {
    flex: 1,
    height: '38px',
    margin: 0,
    padding: '0 16px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#aaa',
    fontSize: '13px',
    fontWeight: 500,
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  submitBtn: {
    flex: 1,
    height: '38px',
    margin: 0,
    padding: '0 16px',
    background: 'linear-gradient(135deg, #e65c00 0%, #cf5200 100%)',
    border: 'none',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 2px 6px rgba(207, 82, 0, 0.25)',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  error: {
    color: '#e74c3c',
    fontSize: '12px',
    margin: 0,
  },
  errorBox: {
    background: 'rgba(231, 76, 60, 0.15)',
    border: '1px solid #e74c3c',
    borderRadius: '6px',
    padding: '12px',
    color: '#e74c3c',
    fontSize: '13px',
    fontWeight: 500,
    textAlign: 'center',
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    background: '#1a1a2e',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px',
    padding: '20px',
    maxWidth: '320px',
    width: '90%',
  },
  modalText: {
    color: '#fff',
    fontSize: '14px',
    margin: '0 0 8px 0',
  },
  modalEmail: {
    color: '#888',
    fontSize: '13px',
    margin: '0 0 16px 0',
    wordBreak: 'break-all',
  },
  deleteBtn: {
    flex: 1,
    height: '38px',
    margin: 0,
    padding: '0 16px',
    background: 'linear-gradient(135deg, #e74c3c 0%, #c0392b 100%)',
    border: 'none',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 2px 6px rgba(231, 76, 60, 0.25)',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
}
