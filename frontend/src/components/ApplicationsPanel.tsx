import { useState, useEffect } from 'react'
import { GetStartedGraphic } from './Graphic/GetStartedGraphic'
import { LinkedInProfileUpdate } from '../../bindings/foxyapply/internal/store'
import {
  GetLinkedInProfile,
  UpdateLinkedInProfile,
  ListRecentApplications,
  GetApplicationStats,
} from '../../bindings/foxyapply/appservice'

interface ApplicationsPanelProps {
  selectedProfile: number | null
  viewMode: 'wizard' | 'dashboard' | 'settings'
  setViewMode: (mode: 'wizard' | 'dashboard' | 'settings') => void
  refreshKey: number
  liveProgress: Record<string, unknown> | null
}

interface ProfileData {
  email: string
  password: string
  phoneNumber: string
  positions: string[]
  locations: string[]
  remoteOnly: boolean
  profileUrl: string
  yearsExperience: number
  userCity: string
  userState: string
}

// Check which fields are complete
function getCompletionStatus(profile: ProfileData) {
  return {
    contactInfo: !!(profile.phoneNumber && profile.userCity && profile.userState),
    jobPreferences: !!(profile.positions.length > 0 && profile.locations.length > 0),
  }
}

function isProfileComplete(profile: ProfileData): boolean {
  const status = getCompletionStatus(profile)
  return status.contactInfo && status.jobPreferences
}

const WIZARD_STEPS = [
  { id: 'contact', title: 'Contact Info', description: 'Phone and location' },
  { id: 'preferences', title: 'Job Preferences', description: 'Positions and locations to search' },
]

const US_STATES = new Set([
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
  'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
  'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
  'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
  'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
  'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
  'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
  'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
  'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
  'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
])

const STATE_ABBREVIATIONS = new Set([
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
])

function validateLocation(value: string): string | null {
  const parts = value.split(',')
  if (parts.length !== 2) {
    return 'Location must be in the format "City, State" (e.g., Knoxville, Tennessee)'
  }
  const city = parts[0].trim()
  const state = parts[1].trim()
  if (!city) {
    return 'City name is required'
  }
  if (STATE_ABBREVIATIONS.has(state.toUpperCase())) {
    return 'Please spell out the full state name (e.g., Tennessee instead of TN)'
  }
  // Title-case the state for matching
  const titleState = state.replace(/\b\w/g, c => c.toUpperCase())
  if (!US_STATES.has(titleState)) {
    return `"${state}" is not a recognized US state. Please use the full state name (e.g., Tennessee)`
  }
  return null
}

export function ApplicationsPanel({
  selectedProfile,
  setViewMode,
  viewMode,
  refreshKey,
  liveProgress,
}: ApplicationsPanelProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState(0)

  // Form fields
  const [profileData, setProfileData] = useState<ProfileData>({
    email: '',
    password: '',
    phoneNumber: '',
    positions: [],
    locations: [],
    remoteOnly: false,
    profileUrl: '',
    yearsExperience: 0,
    userCity: '',
    userState: '',
  })

  const [positionInput, setPositionInput] = useState('')
  const [locationInput, setLocationInput] = useState('')
  const [locationError, setLocationError] = useState<string | null>(null)

  // Load profile data when selectedProfile changes
  useEffect(() => {
    if (!selectedProfile) return

    const loadProfile = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const profile = await GetLinkedInProfile(selectedProfile)
        if (!profile) {
          setError('Profile not found')
          return
        }
        const data: ProfileData = {
          email: profile.email || '',
          password: profile.password || '',
          phoneNumber: profile.phoneNumber || '',
          positions: profile.positions || [],
          locations: profile.locations || [],
          remoteOnly: profile.remoteOnly || false,
          profileUrl: profile.profileUrl || '',
          yearsExperience: profile.yearsExperience || 0,
          userCity: profile.userCity || '',
          userState: profile.userState || '',
        }
        setProfileData(data)

        // Determine view mode based on profile completion
        if (isProfileComplete(data)) {
          setViewMode('dashboard')
        } else {
          setViewMode('wizard')
          const status = getCompletionStatus(data)
          if (!status.contactInfo) {
            setCurrentStep(0)
          } else if (!status.jobPreferences) {
            setCurrentStep(1)
          }
        }
      } catch (e) {
        setError(`Failed to load profile: ${e}`)
      } finally {
        setIsLoading(false)
      }
    }

    loadProfile()
  }, [selectedProfile])

  const updateField = <K extends keyof ProfileData>(field: K, value: ProfileData[K]) => {
    setProfileData((prev) => ({ ...prev, [field]: value }))
  }

  const handleSaveAndContinue = async () => {
    if (!selectedProfile) return

    setIsSaving(true)
    setError(null)

    try {
      const update = new LinkedInProfileUpdate({
        ...profileData,
      })

      await UpdateLinkedInProfile(selectedProfile, update)

      // If in settings mode, go back to dashboard
      if (viewMode === 'settings') {
        setViewMode('dashboard')
        return
      }

      // Move to next step or complete
      if (currentStep < WIZARD_STEPS.length - 1) {
        setCurrentStep(currentStep + 1)
      } else {
        // Last step completed - check if profile is now complete
        if (isProfileComplete(profileData)) {
          setViewMode('dashboard')
        }
      }
    } catch (e) {
      setError(`Failed to save: ${e}`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const addPosition = () => {
    if (positionInput.trim() && !profileData.positions.includes(positionInput.trim())) {
      updateField('positions', [...profileData.positions, positionInput.trim()])
      setPositionInput('')
    }
  }

  const removePosition = (index: number) => {
    updateField(
      'positions',
      profileData.positions.filter((_, i) => i !== index)
    )
  }

  const addLocation = () => {
    const value = locationInput.trim()
    if (!value) return
    const error = validateLocation(value)
    if (error) {
      setLocationError(error)
      return
    }
    if (!profileData.locations.includes(value)) {
      updateField('locations', [...profileData.locations, value])
    }
    setLocationInput('')
    setLocationError(null)
  }

  const removeLocation = (index: number) => {
    updateField(
      'locations',
      profileData.locations.filter((_, i) => i !== index)
    )
  }

  const canProceed = (): boolean => {
    if (currentStep === 0) {
      return !!(profileData.phoneNumber && profileData.userCity && profileData.userState)
    }
    if (currentStep === 1) {
      return profileData.positions.length > 0 && profileData.locations.length > 0
    }
    return false
  }

  if (!selectedProfile) {
    return <GetStartedGraphic />
  }

  if (isLoading) {
    return (
      <div style={styles.placeholder}>
        <p>Loading profile...</p>
      </div>
    )
  }

  // Show dashboard
  if (viewMode === 'dashboard') {
    return (
      <Dashboard
        profileData={profileData}
        onEditSettings={() => setViewMode('settings')}
        selectedProfile={selectedProfile}
        refreshKey={refreshKey}
        liveProgress={liveProgress}
      />
    )
  }

  // Show settings (full form for editing)
  if (viewMode === 'settings') {
    return (
      <SettingsView
        profileData={profileData}
        updateField={updateField}
        positionInput={positionInput}
        setPositionInput={setPositionInput}
        addPosition={addPosition}
        removePosition={removePosition}
        locationInput={locationInput}
        setLocationInput={setLocationInput}
        addLocation={addLocation}
        removeLocation={removeLocation}
        locationError={locationError}
        setLocationError={setLocationError}
        onSave={handleSaveAndContinue}
        onCancel={() => setViewMode('dashboard')}
        isSaving={isSaving}
        error={error}
      />
    )
  }

  // Show wizard for incomplete profiles
  return (
    <div style={styles.container}>
      {/* Progress Header */}
      <div style={styles.progressHeader}>
        <h2 style={styles.title}>Complete Your Profile</h2>
        <p style={styles.subtitle}>Fill out these details to start applying for jobs</p>

        {/* Step indicators */}
        <div style={styles.stepsContainer}>
          {WIZARD_STEPS.map((step, index) => (
            <div key={step.id} style={styles.stepItem}>
              <div
                style={{
                  ...styles.stepCircle,
                  ...(index < currentStep ? styles.stepComplete : {}),
                  ...(index === currentStep ? styles.stepActive : {}),
                }}
              >
                {index < currentStep ? '✓' : index + 1}
              </div>
              <div style={styles.stepLabel}>
                <span
                  style={{
                    ...styles.stepTitle,
                    ...(index === currentStep ? styles.stepTitleActive : {}),
                  }}
                >
                  {step.title}
                </span>
                <span style={styles.stepDesc}>{step.description}</span>
              </div>
              {index < WIZARD_STEPS.length - 1 && <div style={styles.stepLine} />}
            </div>
          ))}
        </div>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {/* Step Content */}
      <div style={styles.stepContent}>
        {currentStep === 0 && (
          <ContactInfoStep profileData={profileData} updateField={updateField} />
        )}
        {currentStep === 1 && (
          <JobPreferencesStep
            profileData={profileData}
            updateField={updateField}
            positionInput={positionInput}
            setPositionInput={setPositionInput}
            addPosition={addPosition}
            removePosition={removePosition}
            locationInput={locationInput}
            setLocationInput={setLocationInput}
            addLocation={addLocation}
            removeLocation={removeLocation}
          />
        )}
      </div>

      {/* Navigation */}
      <div style={styles.navigation}>
        {currentStep > 0 && (
          <button onClick={handleBack} style={styles.backBtn}>
            Back
          </button>
        )}
        <button
          onClick={handleSaveAndContinue}
          disabled={isSaving || !canProceed()}
          style={{
            ...styles.nextBtn,
            ...(!canProceed() ? styles.btnDisabled : {}),
          }}
        >
          {isSaving
            ? 'Saving...'
            : currentStep === WIZARD_STEPS.length - 1
              ? 'Complete Setup'
              : 'Continue'}
        </button>
      </div>
    </div>
  )
}

// Step 1: Contact Info
function ContactInfoStep({
  profileData,
  updateField,
}: {
  profileData: ProfileData
  updateField: <K extends keyof ProfileData>(field: K, value: ProfileData[K]) => void
}) {
  return (
    <div>
      <h3 style={styles.stepHeading}>Contact Information</h3>
      <p style={styles.stepDescription}>This information will be used when applying to jobs.</p>

      <div style={styles.fieldGroup}>
        <label style={styles.label}>Phone Number *</label>
        <input
          type="tel"
          value={profileData.phoneNumber}
          onChange={(e) => updateField('phoneNumber', e.target.value)}
          style={styles.input}
          placeholder="5551234567"
        />
      </div>

      <div style={styles.row}>
        <div style={styles.fieldGroup}>
          <label style={styles.label}>City *</label>
          <input
            type="text"
            value={profileData.userCity}
            onChange={(e) => updateField('userCity', e.target.value)}
            style={styles.input}
            placeholder="San Francisco"
          />
        </div>
        <div style={styles.fieldGroup}>
          <label style={styles.label}>State *</label>
          <input
            type="text"
            value={profileData.userState}
            onChange={(e) => updateField('userState', e.target.value)}
            style={styles.input}
            placeholder="CA"
          />
        </div>
      </div>

      <div style={styles.fieldGroup}>
        <label style={styles.label}>Years of Experience</label>
        <input
          type="number"
          value={profileData.yearsExperience}
          onChange={(e) => updateField('yearsExperience', parseInt(e.target.value) || 0)}
          style={{ ...styles.input, width: '100px' }}
          min={0}
          max={50}
        />
      </div>
    </div>
  )
}

// Step 2: Job Preferences
function JobPreferencesStep({
  profileData,
  updateField,
  positionInput,
  setPositionInput,
  addPosition,
  removePosition,
  locationInput,
  setLocationInput,
  addLocation,
  removeLocation,
}: {
  profileData: ProfileData
  updateField: <K extends keyof ProfileData>(field: K, value: ProfileData[K]) => void
  positionInput: string
  setPositionInput: (v: string) => void
  addPosition: () => void
  removePosition: (i: number) => void
  locationInput: string
  setLocationInput: (v: string) => void
  addLocation: () => void
  removeLocation: (i: number) => void
}) {
  return (
    <div>
      <h3 style={styles.stepHeading}>Job Search Preferences</h3>
      <p style={styles.stepDescription}>
        Tell us what positions and locations you&apos;re interested in.
      </p>

      <div style={styles.fieldGroup}>
        <label style={styles.label}>Positions to Search *</label>
        <div style={styles.tagInputContainer}>
          <input
            type="text"
            value={positionInput}
            onChange={(e) => setPositionInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addPosition())}
            style={styles.tagInput}
            placeholder="e.g., Software Engineer"
          />
          <button onClick={addPosition} style={styles.addBtn}>
            Add
          </button>
        </div>
        <div style={styles.tagList}>
          {profileData.positions.map((pos, index) => (
            <span key={index} style={styles.tag}>
              {pos}
              <button onClick={() => removePosition(index)} style={styles.tagRemove}>
                ×
              </button>
            </span>
          ))}
        </div>
        {profileData.positions.length === 0 && (
          <span style={styles.hint}>Add at least one position</span>
        )}
      </div>

      <div style={styles.fieldGroup}>
        <label style={styles.label}>Locations to Search *</label>
        <div style={styles.tagInputContainer}>
          <input
            type="text"
            value={locationInput}
            onChange={(e) => setLocationInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addLocation())}
            style={styles.tagInput}
            placeholder="e.g., San Francisco, CA"
          />
          <button onClick={addLocation} style={styles.addBtn}>
            Add
          </button>
        </div>
        <div style={styles.tagList}>
          {profileData.locations.map((loc, index) => (
            <span key={index} style={styles.tag}>
              {loc}
              <button onClick={() => removeLocation(index)} style={styles.tagRemove}>
                ×
              </button>
            </span>
          ))}
        </div>
        {profileData.locations.length === 0 && (
          <span style={styles.hint}>Add at least one location</span>
        )}
      </div>

      <div style={styles.checkboxGroup}>
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={profileData.remoteOnly}
            onChange={(e) => updateField('remoteOnly', e.target.checked)}
            style={styles.checkbox}
          />
          Remote Only
        </label>
        <span style={styles.hint}>Only search for remote positions</span>
      </div>
    </div>
  )
}

// Settings View (for editing complete profile)
function SettingsView({
  profileData,
  updateField,
  positionInput,
  setPositionInput,
  addPosition,
  removePosition,
  locationInput,
  setLocationInput,
  addLocation,
  removeLocation,
  locationError,
  setLocationError,
  onSave,
  onCancel,
  isSaving,
  error,
}: {
  profileData: ProfileData
  updateField: <K extends keyof ProfileData>(field: K, value: ProfileData[K]) => void
  positionInput: string
  setPositionInput: (v: string) => void
  addPosition: () => void
  removePosition: (i: number) => void
  locationInput: string
  setLocationInput: (v: string) => void
  addLocation: () => void
  removeLocation: (i: number) => void
  locationError: string | null
  setLocationError: (v: string | null) => void
  onSave: () => void
  onCancel: () => void
  isSaving: boolean
  error: string | null
}) {
  return (
    <div style={styles.container}>
      <div style={styles.settingsHeader}>
        <h2 style={styles.title}>Profile Settings</h2>
        <button onClick={onCancel} style={styles.backBtn}>
          Back
        </button>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      <div style={styles.stepContent}>
        <h3 style={styles.stepHeading}>Contact Information</h3>
        <div style={styles.fieldGroup}>
          <label style={styles.label}>Phone Number</label>
          <input
            type="tel"
            value={profileData.phoneNumber}
            onChange={(e) => updateField('phoneNumber', e.target.value)}
            style={styles.input}
            placeholder="(555) 123-4567"
          />
        </div>
        <div style={styles.row}>
          <div style={styles.fieldGroup}>
            <label style={styles.label}>City</label>
            <input
              type="text"
              value={profileData.userCity}
              onChange={(e) => updateField('userCity', e.target.value)}
              style={styles.input}
              placeholder="San Francisco"
            />
          </div>
          <div style={styles.fieldGroup}>
            <label style={styles.label}>State</label>
            <input
              type="text"
              value={profileData.userState}
              onChange={(e) => updateField('userState', e.target.value)}
              style={styles.input}
              placeholder="CA"
            />
          </div>
        </div>
        <div style={styles.fieldGroup}>
          <label style={styles.label}>Years of Experience</label>
          <input
            type="number"
            value={profileData.yearsExperience}
            onChange={(e) => updateField('yearsExperience', parseInt(e.target.value) || 0)}
            style={{ ...styles.input, width: '100px' }}
            min={0}
            max={50}
          />
        </div>
      </div>

      <div style={styles.stepContent}>
        <h3 style={styles.stepHeading}>Job Search Preferences</h3>
        <div style={styles.fieldGroup}>
          <label style={styles.label}>Positions to Search</label>
          <div style={styles.tagInputContainer}>
            <input
              type="text"
              value={positionInput}
              onChange={(e) => setPositionInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addPosition())}
              style={styles.tagInput}
              placeholder="e.g., Software Engineer"
            />
            <button onClick={addPosition} style={styles.addBtn}>
              Add
            </button>
          </div>
          <div style={styles.tagList}>
            {profileData.positions.map((pos, index) => (
              <span key={index} style={styles.tag}>
                {pos}
                <button onClick={() => removePosition(index)} style={styles.tagRemove}>
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>

        <div style={styles.fieldGroup}>
          <label style={styles.label}>Locations to Search</label>
          <div style={styles.tagInputContainer}>
            <input
              type="text"
              value={locationInput}
              onChange={(e) => setLocationInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addLocation())}
              style={styles.tagInput}
              placeholder="e.g., San Francisco, CA"
            />
            <button onClick={addLocation} style={styles.addBtn}>
              Add
            </button>
          </div>
          <div style={styles.tagList}>
            {profileData.locations.map((loc, index) => (
              <span key={index} style={styles.tag}>
                {loc}
                <button onClick={() => removeLocation(index)} style={styles.tagRemove}>
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>

        <div style={styles.checkboxGroup}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={profileData.remoteOnly}
              onChange={(e) => updateField('remoteOnly', e.target.checked)}
              style={styles.checkbox}
            />
            Remote Only
          </label>
        </div>
      </div>

      <div style={styles.navigation}>
        <button onClick={onCancel} style={styles.backBtn}>
          Cancel
        </button>
        <button onClick={onSave} disabled={isSaving} style={styles.nextBtn}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}

interface ApplicationRecord {
  id: number
  profileId: number
  jobId: string
  title: string
  company: string
  status: string
  errorMessage: string
  appliedAt: string
}

interface StatsRecord {
  applied: number
  failed: number
  total: number
}

type StatsPeriod = 'today' | 'week' | 'all'

// Dashboard (shown when profile is complete)
function Dashboard({
  profileData,
  onEditSettings,
  selectedProfile,
  refreshKey,
  liveProgress,
}: {
  profileData: ProfileData
  onEditSettings: () => void
  selectedProfile: number | null
  refreshKey: number
  liveProgress: Record<string, unknown> | null
}) {
  const [applications, setApplications] = useState<ApplicationRecord[]>([])
  const [stats, setStats] = useState<Record<StatsPeriod, StatsRecord>>({
    today: { applied: 0, failed: 0, total: 0 },
    week: { applied: 0, failed: 0, total: 0 },
    all: { applied: 0, failed: 0, total: 0 },
  })
  const [statsPeriod, setStatsPeriod] = useState<StatsPeriod>('today')

  useEffect(() => {
    if (!selectedProfile) return

    const fetchData = async () => {
      try {
        const apps = await ListRecentApplications(selectedProfile, 50)
        setApplications((apps as ApplicationRecord[]) || [])
      } catch (e) {
        console.error('Failed to fetch applications:', e)
      }

      try {
        const [today, week, all] = await Promise.all([
          GetApplicationStats(selectedProfile, 'today'),
          GetApplicationStats(selectedProfile, 'week'),
          GetApplicationStats(selectedProfile, 'all'),
        ])
        setStats({
          today: (today as StatsRecord) || { applied: 0, failed: 0, total: 0 },
          week: (week as StatsRecord) || { applied: 0, failed: 0, total: 0 },
          all: (all as StatsRecord) || { applied: 0, failed: 0, total: 0 },
        })
      } catch (e) {
        console.error('Failed to fetch stats:', e)
      }
    }

    fetchData()
  }, [selectedProfile, refreshKey])

  const currentStats = stats[statsPeriod]

  return (
    <div style={styles.dashboard}>
      <div style={styles.dashboardHeader}>
        <h2 style={styles.title}>Dashboard</h2>
        <button onClick={onEditSettings} style={styles.settingsBtn}>
          Settings
        </button>
      </div>

      {/* Live Progress */}
      {liveProgress && (
        <div style={styles.progressCard}>
          <div style={styles.progressInfo}>
            <span style={styles.progressLabel}>
              {(liveProgress.message as string) || 'Applying...'}
            </span>
            {typeof liveProgress.current === 'number' && typeof liveProgress.total === 'number' && (
              <span style={styles.progressCount}>
                {liveProgress.current} / {liveProgress.total}
              </span>
            )}
          </div>
          {typeof liveProgress.current === 'number' && typeof liveProgress.total === 'number' && (liveProgress.total as number) > 0 && (
            <div style={styles.progressBarBg}>
              <div
                style={{
                  ...styles.progressBarFill,
                  width: `${Math.min(100, ((liveProgress.current as number) / (liveProgress.total as number)) * 100)}%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Metrics */}
      <div style={styles.metricsSection}>
        <div style={styles.periodToggle}>
          {(['today', 'week', 'all'] as StatsPeriod[]).map((p) => (
            <button
              key={p}
              onClick={() => setStatsPeriod(p)}
              style={{
                ...styles.periodBtn,
                ...(statsPeriod === p ? styles.periodBtnActive : {}),
              }}
            >
              {p === 'today' ? 'Today' : p === 'week' ? 'This Week' : 'All Time'}
            </button>
          ))}
        </div>
        <div style={styles.metricsRow}>
          <div style={styles.metricCard}>
            <span style={styles.metricValue}>{currentStats.applied}</span>
            <span style={styles.metricLabel}>Applied</span>
          </div>
          <div style={styles.metricCard}>
            <span style={{ ...styles.metricValue, color: currentStats.failed > 0 ? '#e74c3c' : '#0984e3' }}>
              {currentStats.failed}
            </span>
            <span style={styles.metricLabel}>Failed</span>
          </div>
          <div style={styles.metricCard}>
            <span style={styles.metricValue}>{currentStats.total}</span>
            <span style={styles.metricLabel}>Total</span>
          </div>
        </div>
      </div>

      {/* Profile Summary */}
      <div style={styles.summaryCard}>
        <h3 style={styles.summaryTitle}>Profile Summary</h3>
        <div style={styles.summaryGrid}>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Location</span>
            <span style={styles.summaryValue}>
              {profileData.userCity}, {profileData.userState}
            </span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Experience</span>
            <span style={styles.summaryValue}>{profileData.yearsExperience} years</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Searching For</span>
            <span style={styles.summaryValue}>{profileData.positions.join(', ')}</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>In Locations</span>
            <span style={styles.summaryValue}>{profileData.locations.join(', ')}</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Remote Only</span>
            <span style={styles.summaryValue}>{profileData.remoteOnly ? 'Yes' : 'No'}</span>
          </div>
        </div>
      </div>

      {/* Recent Applications */}
      <div style={styles.applicationsCard}>
        <h3 style={styles.summaryTitle}>Recent Applications</h3>
        {applications.length === 0 ? (
          <div style={styles.emptyState}>
            <p>No applications yet</p>
            <p style={styles.emptyHint}>Start the browser to begin applying for jobs</p>
          </div>
        ) : (
          <div style={styles.applicationsList}>
            {applications.map((app) => (
              <div key={app.id} style={styles.applicationRow}>
                <div style={styles.applicationInfo}>
                  <span style={styles.applicationTitle}>{app.title || 'Untitled'}</span>
                  <span style={styles.applicationCompany}>{app.company || 'Unknown company'}</span>
                </div>
                <div style={styles.applicationMeta}>
                  <span
                    style={{
                      ...styles.statusBadge,
                      ...(app.status === 'applied' ? styles.statusApplied : styles.statusFailed),
                    }}
                  >
                    {app.status === 'applied' ? 'Applied' : 'Failed'}
                  </span>
                  <span style={styles.applicationTime}>
                    {new Date(app.appliedAt).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: '800px',
    padding: '24px',
  },
  placeholder: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: '#666',
    fontSize: '16px',
  },
  progressHeader: {
    marginBottom: '32px',
  },
  title: {
    fontSize: '24px',
    fontWeight: 600,
    color: '#fff',
    marginBottom: '8px',
  },
  subtitle: {
    fontSize: '14px',
    color: '#888',
    marginBottom: '24px',
  },
  stepsContainer: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0',
  },
  stepItem: {
    display: 'flex',
    alignItems: 'center',
    flex: 1,
  },
  stepCircle: {
    width: '32px',
    height: '32px',
    borderRadius: '50%',
    background: 'rgba(255,255,255,0.1)',
    border: '2px solid rgba(255,255,255,0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#666',
    fontSize: '14px',
    fontWeight: 600,
    flexShrink: 0,
  },
  stepComplete: {
    background: '#00b894',
    borderColor: '#00b894',
    color: '#fff',
  },
  stepActive: {
    borderColor: '#0984e3',
    color: '#0984e3',
  },
  stepLabel: {
    marginLeft: '12px',
    marginRight: '12px',
  },
  stepTitle: {
    display: 'block',
    fontSize: '13px',
    fontWeight: 500,
    color: '#666',
  },
  stepTitleActive: {
    color: '#fff',
  },
  stepDesc: {
    display: 'block',
    fontSize: '11px',
    color: '#555',
  },
  stepLine: {
    flex: 1,
    height: '2px',
    background: 'rgba(255,255,255,0.1)',
    marginRight: '12px',
  },
  stepContent: {
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '24px',
  },
  stepHeading: {
    fontSize: '18px',
    fontWeight: 600,
    color: '#fff',
    marginBottom: '8px',
  },
  stepDescription: {
    fontSize: '14px',
    color: '#888',
    marginBottom: '24px',
  },
  navigation: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '12px',
  },
  backBtn: {
    height: '40px',
    margin: 0,
    padding: '0 20px',
    background: 'rgba(255,255,255,0.08)',
    color: '#fff',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '8px',
    cursor: 'pointer',
    fontSize: '13px',
    lineHeight: 1,
    fontWeight: 500,
    fontFamily: 'inherit',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    whiteSpace: 'nowrap' as const,
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  nextBtn: {
    height: '48px',
    minWidth: '200px',
    margin: 0,
    padding: '0 48px',
    background: 'linear-gradient(135deg, #0984e3 0%, #0770c2 100%)',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    fontSize: '15px',
    lineHeight: 1,
    fontWeight: 600,
    fontFamily: 'inherit',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    whiteSpace: 'nowrap' as const,
    boxShadow: '0 2px 8px rgba(9, 132, 227, 0.3)',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  btnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
    boxShadow: 'none',
  },
  fieldGroup: {
    marginBottom: '20px',
    flex: 1,
  },
  label: {
    display: 'block',
    fontSize: '13px',
    fontWeight: 500,
    color: '#aaa',
    marginBottom: '8px',
  },
  input: {
    width: '100%',
    height: '42px',
    padding: '0 14px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  hint: {
    display: 'block',
    fontSize: '12px',
    color: '#666',
    marginTop: '6px',
  },
  row: {
    display: 'flex',
    gap: '16px',
  },
  tagInputContainer: {
    display: 'flex',
    gap: '8px',
  },
  tagInput: {
    flex: 1,
    height: '42px',
    padding: '0 14px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  addBtn: {
    height: '42px',
    padding: '0 20px',
    background: 'rgba(255,255,255,0.1)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '13px',
    fontWeight: 500,
    fontFamily: 'inherit',
    textAlign: 'center' as const,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
  },
  tagList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    marginTop: '12px',
  },
  tag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 12px',
    background: 'rgba(9, 132, 227, 0.2)',
    border: '1px solid rgba(9, 132, 227, 0.4)',
    borderRadius: '20px',
    color: '#74b9ff',
    fontSize: '13px',
  },
  tagRemove: {
    background: 'none',
    border: 'none',
    color: '#74b9ff',
    fontSize: '16px',
    cursor: 'pointer',
    padding: '0',
    lineHeight: 1,
  },
  checkboxGroup: {
    marginTop: '20px',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    color: '#fff',
    fontSize: '14px',
    cursor: 'pointer',
  },
  checkbox: {
    width: '18px',
    height: '18px',
    cursor: 'pointer',
  },
  errorBox: {
    background: 'rgba(231, 76, 60, 0.15)',
    border: '1px solid #e74c3c',
    borderRadius: '6px',
    padding: '12px',
    color: '#e74c3c',
    fontSize: '13px',
    marginBottom: '20px',
  },
  // Dashboard styles
  dashboard: {
    padding: '24px',
    maxWidth: '800px',
  },
  dashboardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '24px',
  },
  settingsHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '24px',
  },
  settingsBtn: {
    height: '36px',
    margin: 0,
    padding: '0 14px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '13px',
    lineHeight: 1,
    fontWeight: 500,
    fontFamily: 'inherit',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxSizing: 'border-box' as const,
    overflow: 'hidden',
  },
  metricsRow: {
    display: 'flex',
    gap: '16px',
    marginBottom: '24px',
  },
  metricCard: {
    flex: 1,
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '12px',
    padding: '24px',
    textAlign: 'center',
  },
  metricValue: {
    display: 'block',
    fontSize: '36px',
    fontWeight: 700,
    color: '#0984e3',
    marginBottom: '8px',
  },
  metricLabel: {
    fontSize: '14px',
    color: '#888',
  },
  summaryCard: {
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '12px',
    padding: '20px',
    marginBottom: '24px',
  },
  summaryTitle: {
    fontSize: '14px',
    fontWeight: 600,
    color: '#888',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '16px',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '16px',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  summaryLabel: {
    fontSize: '12px',
    color: '#666',
  },
  summaryValue: {
    fontSize: '14px',
    color: '#fff',
  },
  applicationsCard: {
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '12px',
    padding: '20px',
  },
  emptyState: {
    textAlign: 'center',
    padding: '32px',
    color: '#666',
  },
  emptyHint: {
    fontSize: '13px',
    color: '#555',
    marginTop: '8px',
  },
  // Progress card
  progressCard: {
    background: 'rgba(9, 132, 227, 0.1)',
    border: '1px solid rgba(9, 132, 227, 0.3)',
    borderRadius: '12px',
    padding: '16px 20px',
    marginBottom: '24px',
  },
  progressInfo: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
  },
  progressLabel: {
    fontSize: '14px',
    color: '#74b9ff',
    fontWeight: 500,
  },
  progressCount: {
    fontSize: '13px',
    color: '#888',
  },
  progressBarBg: {
    height: '6px',
    borderRadius: '3px',
    background: 'rgba(255,255,255,0.1)',
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    borderRadius: '3px',
    background: 'linear-gradient(90deg, #0984e3, #74b9ff)',
    transition: 'width 0.3s ease',
  },
  // Metrics section
  metricsSection: {
    marginBottom: '24px',
  },
  periodToggle: {
    display: 'flex',
    gap: '4px',
    marginBottom: '12px',
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '8px',
    padding: '4px',
  },
  periodBtn: {
    flex: 1,
    height: '32px',
    padding: '0 16px',
    background: 'transparent',
    border: 'none',
    borderRadius: '6px',
    color: '#888',
    fontSize: '12px',
    fontWeight: 500,
    fontFamily: 'inherit',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  periodBtnActive: {
    background: 'rgba(9, 132, 227, 0.2)',
    color: '#74b9ff',
  },
  // Applications list
  applicationsList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '2px',
  },
  applicationRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 0',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  },
  applicationInfo: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '2px',
    minWidth: 0,
    flex: 1,
  },
  applicationTitle: {
    fontSize: '14px',
    color: '#fff',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  applicationCompany: {
    fontSize: '12px',
    color: '#888',
  },
  applicationMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    flexShrink: 0,
    marginLeft: '16px',
  },
  statusBadge: {
    fontSize: '11px',
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: '12px',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
  },
  statusApplied: {
    background: 'rgba(0, 184, 148, 0.15)',
    color: '#00b894',
  },
  statusFailed: {
    background: 'rgba(231, 76, 60, 0.15)',
    color: '#e74c3c',
  },
  applicationTime: {
    fontSize: '12px',
    color: '#666',
    whiteSpace: 'nowrap' as const,
  },
}
