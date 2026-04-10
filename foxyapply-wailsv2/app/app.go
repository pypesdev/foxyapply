package app

import (
	"context"
	"fmt"
	"sync"

	"applyfox/internal/automation"
	"applyfox/internal/browser"
	"applyfox/internal/store"

	"github.com/go-rod/rod"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

type App struct {
	ctx        context.Context
	store      *store.Store
	browser    *browser.BrowserManager
	downloader *browser.ChromeDownloader
	engine     *automation.Engine
	pages      map[string]*rod.Page
	pagesMu    sync.RWMutex
	pageID     int
	profiles   map[string]*store.LinkedInProfile
	profilesMu sync.RWMutex
	profileID  int
}

func NewApp() *App {
	return &App{
		browser:    browser.NewBrowserManager(nil),
		downloader: browser.NewChromeDownloader(),
		pages:      make(map[string]*rod.Page),
	}
}

func (a *App) Startup(ctx context.Context) {
	a.ctx = ctx
	s, err := store.New()
	fmt.Println("✅ App started")
	if err != nil {
		runtime.LogError(ctx, fmt.Sprintf("Failed to initialize store: %v", err))
	} else {
		a.store = s
	}
}

func (a *App) Shutdown(ctx context.Context) {
	if a.store != nil {
		a.store.Close()
	}
	a.browser.Close()
}

type BrowserStatus struct {
	Running    bool   `json:"running"`
	Applying   bool   `json:"applying"`
	Headless   bool   `json:"headless"`
	PageCount  int    `json:"pageCount"`
	Downloaded bool   `json:"downloaded"`
	Version    string `json:"version"`
}

func (a *App) GetBrowserStatus() BrowserStatus {
	a.pagesMu.RLock()
	pageCount := len(a.pages)
	a.pagesMu.RUnlock()
	return BrowserStatus{
		Running:    a.browser.IsRunning(),
		Applying:   a.browser.IsApplying(),
		PageCount:  pageCount,
		Downloaded: a.downloader.IsDownloaded(),
		Version:    a.downloader.Version,
	}
}

func (a *App) StartBrowser(email, password string) (bool, error) {
	err := a.browser.Launch()
	if err != nil {
		return false, err
	}
	successfulLogin, _, err := a.browser.Login(email, password)
	a.browser.Close()
	runtime.EventsEmit(a.ctx, "browser:started", nil)
	return successfulLogin, nil
}

func (a *App) StartApplying(profileId int) error {
	profile, err := a.store.GetLinkedInProfile(int64(profileId))
	if err != nil {
		return fmt.Errorf("failed to get LinkedIn profile: %w", err)
	}
	err = a.browser.Launch()
	if err != nil {
		return err
	}

	successfulLogin, page, err := a.browser.Login(profile.Email, profile.Password)
	a.browser.StartApplying(profile, page)
	fmt.Println("✅ Logged in to LinkedIn: ", successfulLogin)
	if err != nil {
		return err
	}
	return nil
}

func (a *App) StopBrowser() error {
	a.pagesMu.Lock()
	for id := range a.pages {
		delete(a.pages, id)
	}
	a.pagesMu.Unlock()

	err := a.browser.Close()
	if err != nil {
		return err
	}

	a.browser.SetApplying(false)
	runtime.EventsEmit(a.ctx, "browser:stopped", nil)
	return nil
}

// DownloadBrowser downloads Chrome for Testing
func (a *App) DownloadBrowser() error {
	// Emit progress events
	progressFn := func(downloaded, total int64) {
		percent := float64(downloaded) / float64(total) * 100
		runtime.EventsEmit(a.ctx, "browser:download-progress", map[string]interface{}{
			"downloaded": downloaded,
			"total":      total,
			"percent":    percent,
		})
	}

	err := a.downloader.Download(progressFn)
	if err != nil {
		return err
	}

	runtime.EventsEmit(a.ctx, "browser:downloaded", nil)
	return nil
}

// ============================================================================
// Store Methods (Persistence)
// ============================================================================

// CreateLinkedInProfile creates a new LinkedIn profile
func (a *App) CreateLinkedInProfile(email, password string) (*store.LinkedInProfile, error) {
	if a.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return a.store.CreateLinkedInProfile(email, password)
}

// GetLinkedInProfile retrieves a LinkedIn profile by ID
func (a *App) GetLinkedInProfile(id int64) (*store.LinkedInProfile, error) {
	if a.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return a.store.GetLinkedInProfile(id)
}

// ListLinkedInProfiles retrieves all LinkedIn profiles
func (a *App) ListLinkedInProfiles() ([]*store.LinkedInProfile, error) {
	if a.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return a.store.ListLinkedInProfiles()
}

// UpdateLinkedInProfile updates an existing LinkedIn profile
func (a *App) UpdateLinkedInProfile(id int64, update store.LinkedInProfileUpdate) (*store.LinkedInProfile, error) {
	if a.store == nil {
		return nil, fmt.Errorf("store not initialized")
	}
	return a.store.UpdateLinkedInProfile(id, update)
}

// DeleteLinkedInProfile deletes a LinkedIn profile
func (a *App) DeleteLinkedInProfile(id int64) error {
	if a.store == nil {
		return fmt.Errorf("store not initialized")
	}
	return a.store.DeleteLinkedInProfile(id)
}

func (a *App) SetApplying(applying bool) {
	a.browser.SetApplying(applying)
}
