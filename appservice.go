package main

import (
	"context"
	"fmt"
	"foxyapply/internal/browser"
	"foxyapply/internal/store"

	"github.com/wailsapp/wails/v3/pkg/application"
)

type AppService struct {
	app        *application.App
	store      *store.Store
	browser    *browser.BrowserManager
	downloader *browser.ChromeDownloader
}

func (s *AppService) ServiceStartup(ctx context.Context, options application.ServiceOptions) error {
	s.app = application.Get()
	s.browser = browser.NewBrowserManager(nil)
	s.downloader = browser.NewChromeDownloader()

	store, err := store.New()
	fmt.Println("✅ App started")
	if err != nil {
		fmt.Println("❌ Failed to initialize store:", err)
	} else {
		s.store = store
	}
	return nil
}

func (s *AppService) ServiceShutdown(ctx context.Context, options application.ServiceOptions) error {
	if s.store != nil {
		s.store.Close()
	}
	fmt.Println("🛑 App shutting down")
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
		Running:    s.browser.IsRunning(),
		Applying:   s.browser.IsApplying(),
		Downloaded: s.downloader.IsDownloaded(),
		Version:    s.downloader.Version,
	}
}

func (s *AppService) StartBrowser(email, password string) (bool, error) {
	err := s.browser.Launch()
	if err != nil {
		return false, err
	}
	successfulLogin, _, err := s.browser.Login(email, password)
	s.browser.Close()
	s.app.Event.Emit("browser:started", nil)
	return successfulLogin, nil
}

func (s *AppService) StartApplying(profileId int) error {
	profile, err := s.store.GetLinkedInProfile(int64(profileId))
	if err != nil {
		return fmt.Errorf("failed to get LinkedIn profile: %w", err)
	}
	err = s.browser.Launch()
	if err != nil {
		return err
	}

	successfulLogin, page, err := s.browser.Login(profile.Email, profile.Password)
	if err != nil {
		return err
	}
	if !successfulLogin {
		return fmt.Errorf("failed to log in to LinkedIn")
	}
	fmt.Println("✅ Logged in to LinkedIn")
	s.browser.StartApplying(profile, page)
	return nil
}

func (s *AppService) StopBrowser() error {
	err := s.browser.Close()
	if err != nil {
		return err
	}

	s.browser.SetApplying(false)
	s.app.Event.Emit("browser:stopped", nil)
	return nil
}

func (s *AppService) DownloadBrowser() error {
	// Emit progress events
	progressFn := func(downloaded, total int64) {
		percent := float64(downloaded) / float64(total) * 100
		s.app.Event.Emit("browser:download-progress", map[string]interface{}{
			"downloaded": downloaded,
			"total":      total,
			"percent":    percent,
		})
	}

	err := s.downloader.Download(progressFn)
	if err != nil {
		return err
	}

	s.app.Event.Emit("browser:downloaded", nil)
	return nil
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
	s.browser.SetApplying(applying)
}
