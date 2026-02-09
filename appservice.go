package main

import (
	"context"
	"fmt"
	"foxyapply/internal/pybot"
	"foxyapply/internal/store"
	"sync/atomic"
	"time"

	"github.com/wailsapp/wails/v3/pkg/application"
)

type AppService struct {
	app             *application.App
	store           *store.Store
	bot             *pybot.Manager
	activeProfileID atomic.Int64
}

func (s *AppService) ServiceStartup(ctx context.Context, options application.ServiceOptions) error {
	s.app = application.Get()
	s.bot = pybot.NewManager("")
	s.bot.SetEventHandler(s.handleBotEvent)

	store, err := store.New()
	fmt.Println("App started")
	if err != nil {
		fmt.Println("Failed to initialize store:", err)
	} else {
		s.store = store
	}
	return nil
}

func (s *AppService) ServiceShutdown(ctx context.Context, options application.ServiceOptions) error {
	if s.bot != nil {
		_ = s.bot.Stop()
	}
	if s.store != nil {
		s.store.Close()
	}
	fmt.Println("App shutting down")
	return nil
}

type BrowserStatus struct {
	Running    bool   `json:"running"`
	Applying   bool   `json:"applying"`
	Headless   bool   `json:"headless"`
	Downloaded bool   `json:"downloaded"`
	Version    string `json:"version"`
}

func (s *AppService) GetBrowserStatus() BrowserStatus {
	return BrowserStatus{
		Running:    s.bot.IsRunning(),
		Applying:   s.bot.IsApplying(),
		Downloaded: true, // PyInstaller binary is pre-bundled
		Version:    "selenium",
	}
}

func (s *AppService) StartBrowser(email, password string) (bool, error) {
	// Login now happens inside Python's /start — just return success.
	return true, nil
}

func (s *AppService) StartApplying(profileId int) error {
	profile, err := s.store.GetLinkedInProfile(int64(profileId))
	if err != nil {
		return fmt.Errorf("failed to get LinkedIn profile: %w", err)
	}

	// Start the bot process if not already running
	if !s.bot.IsRunning() {
		if err := s.bot.Start(); err != nil {
			return fmt.Errorf("failed to start bot: %w", err)
		}
	}

	if err := s.bot.StartApplying(profile); err != nil {
		return fmt.Errorf("failed to start applying: %w", err)
	}

	s.activeProfileID.Store(int64(profileId))
	s.app.Event.Emit("browser:started", nil)
	return nil
}

func (s *AppService) StopBrowser() error {
	if err := s.bot.Stop(); err != nil {
		return err
	}
	s.app.Event.Emit("browser:stopped", nil)
	return nil
}

func (s *AppService) DownloadBrowser() error {
	// No-op: PyInstaller binary is pre-bundled with the app.
	return nil
}

// handleBotEvent routes Python bot WebSocket events to Wails frontend events.
func (s *AppService) handleBotEvent(event pybot.BotEvent) {
	switch event.Type {
	case pybot.EventBotStarted:
		s.app.Event.Emit("browser:started", nil)
	case pybot.EventBotStopped:
		s.bot.SetApplying(false)
		s.activeProfileID.Store(0)
		s.app.Event.Emit("browser:stopped", event.Data)
	case pybot.EventLoginFailed:
		_ = s.bot.Stop()
		s.activeProfileID.Store(0)
		s.app.Event.Emit("browser:stopped", event.Data)
	case pybot.EventJobApplied:
		s.persistApplication(event.Data, "applied", "")
		s.app.Event.Emit("bot:job-applied", event.Data)
	case pybot.EventJobFailed:
		errMsg, _ := event.Data["error"].(string)
		s.persistApplication(event.Data, "failed", errMsg)
		s.app.Event.Emit("bot:job-failed", event.Data)
	case pybot.EventProgress:
		s.app.Event.Emit("bot:progress", event.Data)
	case pybot.EventLog:
		s.app.Event.Emit("bot:log", event.Data)
	case pybot.EventError:
		s.app.Event.Emit("bot:error", event.Data)
	}
}

// ============================================================================
// Store Methods (Persistence)
// ============================================================================

// CreateLinkedInProfile creates a new LinkedIn profile
func (s *AppService) CreateLinkedInProfile(email, password string) (*store.LinkedInProfile, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return s.store.CreateLinkedInProfile(email, password)
}

// GetLinkedInProfile retrieves a LinkedIn profile by ID
func (s *AppService) GetLinkedInProfile(id int64) (*store.LinkedInProfile, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return s.store.GetLinkedInProfile(id)
}

// ListLinkedInProfiles retrieves all LinkedIn profiles
func (s *AppService) ListLinkedInProfiles() ([]*store.LinkedInProfile, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return s.store.ListLinkedInProfiles()
}

// UpdateLinkedInProfile updates an existing LinkedIn profile
func (s *AppService) UpdateLinkedInProfile(id int64, update store.LinkedInProfileUpdate) (*store.LinkedInProfile, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return s.store.UpdateLinkedInProfile(id, update)
}

// DeleteLinkedInProfile deletes a LinkedIn profile
func (s *AppService) DeleteLinkedInProfile(id int64) error {
	if s.store == nil {
		return fmt.Errorf("store not initialized")
	}
	return s.store.DeleteLinkedInProfile(id)
}

func (s *AppService) SetApplying(applying bool) {
	s.bot.SetApplying(applying)
}

// persistApplication saves a job application event to the store.
func (s *AppService) persistApplication(data map[string]interface{}, status, errorMessage string) {
	if s.store == nil {
		return
	}
	profileID := s.activeProfileID.Load()
	if profileID == 0 {
		return
	}
	jobID, _ := data["job_id"].(string)
	title, _ := data["title"].(string)
	company, _ := data["company"].(string)
	_, err := s.store.CreateJobApplication(profileID, jobID, title, company, status, errorMessage)
	if err != nil {
		fmt.Println("Failed to persist application:", err)
	}
}

// ListRecentApplications returns recent job applications for a profile
func (s *AppService) ListRecentApplications(profileID int64, limit int) ([]*store.JobApplication, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return s.store.ListRecentApplications(profileID, limit)
}

// GetApplicationStats returns aggregate application stats for a profile
func (s *AppService) GetApplicationStats(profileID int64, period string) (*store.ApplicationStats, error) {
	if s.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}

	var since time.Time
	now := time.Now()
	switch period {
	case "today":
		since = time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, now.Location())
	case "week":
		since = now.AddDate(0, 0, -7)
	default: // "all"
		// since stays zero-valued → no time filter
	}

	return s.store.GetApplicationStats(profileID, since)
}
