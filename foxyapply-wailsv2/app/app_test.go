package app

import (
	"testing"
)

func TestNewApp(t *testing.T) {
	app := NewApp()

	if app == nil {
		t.Fatal("NewApp() returned nil")
	}

	if app.pages == nil {
		t.Error("pages map not initialized")
	}

	if app.browser == nil {
		t.Error("browser manager not initialized")
	}

	if app.downloader == nil {
		t.Error("downloader not initialized")
	}
}

func TestGetBrowserStatus_NotRunning(t *testing.T) {
	app := NewApp()

	status := app.GetBrowserStatus()

	if status.Running {
		t.Error("expected browser to not be running")
	}

	if status.PageCount != 0 {
		t.Errorf("expected 0 pages, got %d", status.PageCount)
	}
}

func TestNewPage_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	_, err := app.NewPage()

	if err == nil {
		t.Error("expected error when browser not running")
	}

	if err.Error() != "browser not running" {
		t.Errorf("unexpected error message: %s", err.Error())
	}
}

func TestClosePage_PageNotFound(t *testing.T) {
	app := NewApp()

	err := app.ClosePage("nonexistent")

	if err == nil {
		t.Error("expected error for nonexistent page")
	}
}

func TestGetPages_Empty(t *testing.T) {
	app := NewApp()

	pages := app.GetPages()

	if len(pages) != 0 {
		t.Errorf("expected empty pages, got %d", len(pages))
	}
}

func TestNavigate_PageNotFound(t *testing.T) {
	app := NewApp()

	err := app.Navigate("nonexistent", "https://example.com")

	if err == nil {
		t.Error("expected error for nonexistent page")
	}
}

func TestClick_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	err := app.Click("page-1", "#button")

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestType_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	err := app.Type("page-1", "#input", "text")

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestScreenshot_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	_, err := app.Screenshot("page-1", false)

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestEval_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	_, err := app.Eval("page-1", "return 1")

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestGetText_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	_, err := app.GetText("page-1", "#element")

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestExecuteScript_BrowserNotRunning(t *testing.T) {
	app := NewApp()

	_, err := app.ExecuteScript("page-1", `{"actions":[]}`)

	if err == nil {
		t.Error("expected error when browser not running")
	}
}

func TestExecuteScript_InvalidJSON(t *testing.T) {
	app := NewApp()
	// Simulate engine being set (browser was started)
	// This test would need the engine to be non-nil to test JSON parsing

	// For now, test that browser not running error takes precedence
	_, err := app.ExecuteScript("page-1", "invalid json")

	if err == nil {
		t.Error("expected error")
	}
}
