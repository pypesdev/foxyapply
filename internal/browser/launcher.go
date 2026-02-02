package browser

import (
	"context"
	"errors"
	"fmt"
	"foxyapply/internal/store"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/input"
	"github.com/go-rod/rod/lib/launcher"
	"github.com/go-rod/rod/lib/proto"
	"github.com/go-rod/stealth"
)

// BrowserManager handles Chrome/Chromium lifecycle
type BrowserManager struct {
	cfg        *Config
	browser    *rod.Browser
	launcher   *launcher.Launcher
	controlURL string
	mu         sync.RWMutex
	ctx        context.Context
	cancel     context.CancelFunc
}

// Config holds browser configuration options
type Config struct {
	Headless   bool
	IsApplying bool   // Whether the browser is used for applying
	BrowserBin string // Custom browser binary path
	UserData   string // Custom user data directory
}

// NewBrowserManager creates a new browser manager instance
func NewBrowserManager(cfg *Config) *BrowserManager {
	if cfg == nil {
		cfg = &Config{Headless: false}
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &BrowserManager{
		cfg:    cfg,
		ctx:    ctx,
		cancel: cancel,
	}
}

// Launch starts the browser process
func (bm *BrowserManager) Launch() error {
	bm.mu.Lock()
	defer bm.mu.Unlock()

	if bm.browser != nil {
		return fmt.Errorf("browser already running")
	}

	// Create launcher with options
	l := launcher.New().
		NoSandbox(true).           // --no-sandbox
		Set("start-maximized").    // Start maximized
		Set("disable-extensions"). // Disable infobars
		Set("disable-blink-features").
		Set("disable-blink-features", "AutomationControlled").
		Set("useAutomationExtension", "false").
		Set("excludeSwitches", "enable-automation").
		Headless(false). // Run in non-headless mode for visibility
		Devtools(false)  // Keep devtools closed to appear more normal

	// Try to find browser in order of preference:
	// 1. Bundled browser
	// 2. System Chrome
	// 3. Auto-download (Rod default)
	if bundledPath := bm.findBundledBrowser(); bundledPath != "" {
		l = l.Bin(bundledPath)
	} else if systemPath := bm.findSystemBrowser(); systemPath != "" {
		l = l.Bin(systemPath)
	}
	// If neither found, Rod will auto-download

	// Launch the browser
	url, err := l.Launch()
	if err != nil {
		return fmt.Errorf("failed to launch browser: %w", err)
	}

	bm.controlURL = url
	bm.launcher = l

	// Connect to browser
	bm.browser = rod.New().ControlURL(url)
	if err := bm.browser.Connect(); err != nil {
		return fmt.Errorf("failed to connect to browser: %w", err)
	}
	bm.browser.MustIgnoreCertErrors(true)
	return nil
}

func (bm *BrowserManager) Login(email, password string) (successfulLogin bool, initPage *rod.Page, err error) {
	page := stealth.MustPage(bm.browser)

	page.MustNavigate("https://linkedin.com")
	time.Sleep(300 * time.Millisecond)
	page.MustNavigate("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
	// 1. Find username field and input email
	userField := page.MustElement("#username")
	userField.MustInput(email)

	// 2. Press Tab
	userField.MustWaitInteractable()
	page.Keyboard.Press(input.Tab)

	// 3. Wait 2 seconds (or use a better wait if possible)
	page.MustWaitRequestIdle() // or
	time.Sleep(2 * time.Second)

	// 4. Find password field and input password
	pwField := page.MustElement("#password")
	pwField.MustInput(password)

	// 5. Wait 2 seconds
	page.MustWaitRequestIdle() // or
	time.Sleep(2 * time.Second)

	// 6. Find login button and click
	loginButton := page.MustElement(".btn__primary--large")
	loginButton.MustClick()

	// 7. Wait 3 seconds
	page.MustWaitRequestIdle() // or
	time.Sleep(3 * time.Second)

	loggedInElement, errorLoggingIn := page.Timeout(15 * time.Second).Element("#caret-small") // 8. Check for element by id with timeout
	if errorLoggingIn != nil || loggedInElement == nil {
		bm.browser.Close()
		bm.browser = nil
		bm.cancel()
		return false, nil, nil
	}

	return true, page, nil
}

func (bm *BrowserManager) StartApplying(profile *store.LinkedInProfile, page *rod.Page) error {
	bm.SetApplying(true)
	rand.Seed(time.Now().UnixNano())
	position := profile.Positions[rand.Intn(len(profile.Positions))]
	location := profile.Locations[rand.Intn(len(profile.Locations))]
	jobsPerPage := 0
	IDs := []int{}
	fmt.Printf("⚪ Starting application bot with position: %s in location: %s\n", position, location)
	for {
		jobsPageUrl := fmt.Sprintf("https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=%s&location=%s&sortBy=DD&start=%d",
			position, location, jobsPerPage)
		page.MustNavigate(jobsPageUrl)
		time.Sleep(1 * time.Second) // Add a delay to let jobs page load
		if _, err := bm.LoadPage(page); err != nil {
			return fmt.Errorf("failed to load page: %w", err)
		}
		links := page.MustElementsX("//div[@data-job-id]")
		if links.Empty() {
			return fmt.Errorf("No job links found, stopping application process.")
		}
		for _, element := range links {
			children := element.MustElementsX(".//a[contains(@class, 'job-card-container__link')]")
			for _, child := range children {
				jobLink := child.MustAttribute("href")
				jobID, ok := ExtractJobID(*jobLink)
				if !ok {
					fmt.Printf("Failed to extract job ID from link: %s\n", *jobLink)
					continue
				}
				IDs = append(IDs, jobID)
			}
		}
		for _, jobID := range IDs {
			fmt.Printf("⚪ Applying to job ID: %d\n", jobID)
			page.MustNavigate(fmt.Sprintf("https://www.linkedin.com/jobs/view/%d", jobID))
			time.Sleep(2 * time.Second)
			_, err := bm.GetEasyApplyButton(page)
			if err != nil {
				fmt.Printf("❌ No Easy Apply button for job ID %d: %v\n", jobID, err)
				continue
			}
			fmt.Printf("⚪ Found Easy Apply button for job ID %d, attempting to apply...\n", jobID)
			_, err = bm.FillOutEasyApplyForm(page, profile)
			if err != nil {
				fmt.Printf("❌ Failed to apply for job ID %d: %v\n", jobID, err)
			} else {
				fmt.Printf("✅ Successfully applied for job ID %d\n", jobID)
			}
		}
	}
}

func (bm *BrowserManager) LoadPage(page *rod.Page) (*goquery.Document, error) {
	// Find the job list container and hover over it so scroll targets it
	jobList, err := page.Element(".scaffold-layout__list")
	if err != nil {
		fmt.Printf("Could not find job list container: %v\n", err)
		return nil, err
	}
	if err := jobList.Hover(); err != nil {
		fmt.Printf("Could not hover over job list: %v\n", err)
		return nil, err
	}

	for i := 0; i < 14; i++ {
		if err := page.Mouse.Scroll(0, 200, 1); err != nil {
			fmt.Printf("Error scrolling on iteration %d: %v\n", i, err)
			return nil, err
		}
		time.Sleep(2 * time.Second)
	}
	html, err := page.HTML()
	if err != nil {
		return nil, err
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return nil, err
	}

	return doc, nil
}

func (bm *BrowserManager) GetEasyApplyButton(page *rod.Page) (bool, error) {
	page.MustWaitLoad()
	buttons := page.MustElementsX(`//*[contains(@aria-label, "Easy Apply to")]`)

	// If you want to click the first one
	if len(buttons) > 0 {
		buttons[0].MustClick()
		return true, nil
	}

	return false, errors.New("Easy Apply button not found")
}
func sleepRand(minSec, maxSec float64) {
	d := minSec + rand.Float64()*(maxSec-minSec)
	time.Sleep(time.Duration(d * float64(time.Second)))
}

func (bm *BrowserManager) FillOutEasyApplyForm(page *rod.Page, profile *store.LinkedInProfile) (bool, error) {
	const (
		nextSel   = `button[aria-label='Continue to next step']`
		reviewSel = `button[aria-label='Review your application']`
		submitSel = `button[aria-label='Submit application']`

		errorMessageSel = `.artdeco-inline-feedback__icon`
		followLabelSel  = `label[for='follow-company-checkbox']`
	)

	type locator struct {
		kind string // "css" or "xpath"
		q    string
	}

	buttons := []locator{
		{kind: "css", q: nextSel}, // i == 0
		{kind: "css", q: reviewSel},
		{kind: "css", q: followLabelSel}, // i == 2 special case
		{kind: "css", q: submitSel},      // i == 3 => submitted
	}

	submitted := false

	isPresent := func(loc locator) bool {
		page.MustWaitLoad()
		_, err := page.Timeout(4 * time.Second).Element(loc.q)
		if err != nil {
			// Check if there are iframes
			iframes := page.MustElements("iframe")
			for _, iframe := range iframes {
				// Switch to iframe context
				frame := iframe.MustFrame()

				// Try to find element in iframe
				if loc.kind == "css" {
					if has, _, _ := frame.Has(loc.q); has {
						return true
					}
				} else {
					if has, _, _ := frame.HasX(loc.q); has {
						return true
					}
				}
			}
		} else {
			return true
		}
		return false
	}

	hasErrors := func() bool {
		return isPresent(locator{kind: "css", q: errorMessageSel})
	}

	handleInlineErrors := func() {
		if !isPresent(locator{kind: "css", q: errorMessageSel}) {
			return
		}
		iframes := page.MustElements("iframe")
		for _, iframe := range iframes {
			// Switch to iframe context
			frame := iframe.MustFrame()

			// Try to find element in iframe
			if has, _, _ := frame.Has(errorMessageSel); has {
				host, err := frame.Element(".jobs-easy-apply-modal")
				if err != nil {
					continue
				}
				if shadowRoot := host.MustShadowRoot(); shadowRoot != nil {
					if err := bm.FillInvalids(shadowRoot, profile, nil); err != nil {
						log.Println("fillInvalids error:", err)
					}
				}
			}
		}

	}

	clickWhenClickable := func(loc locator) error {
		var err error

		p := page.Timeout(2 * time.Second)
		if loc.kind == "xpath" {
			_, err = p.ElementX(loc.q)
		} else {

			_, err = p.Element(loc.q)
		}
		if err != nil {
			iframes := page.MustElements("iframe")
			for _, iframe := range iframes {
				frame := iframe.MustFrame()

				if has, button, _ := frame.Has(loc.q); has {
					_ = button.ScrollIntoView()
					_ = button.Focus()
					return frame.Keyboard.Press(input.Enter)
				}
			}
		}
		return err
	}

	// --- main logic (port of your while True loop) ---
	defer func() {
		// match your final sleep in Python
		sleepRand(1.5, 2.5)
	}()

	sleepRand(1.5, 2.5)

	for i := 0; i < 15 && !submitted; i++ {
		handleInlineErrors()
		for j, loc := range buttons {
			if isPresent(loc) && !hasErrors() {
				if err := clickWhenClickable(loc); err == nil {
					if j == 3 {
						submitted = true
						break
					}
					if j == 0 {
						break
					}
				}
			}
			handleInlineErrors()
		}
	}

	return submitted, nil
}
func attr(el *rod.Element, name string) string {
	v, _ := el.Attribute(name)
	if v == nil {
		return ""
	}
	return strings.TrimSpace(*v)
}

func isEmpty(el *rod.Element) bool {
	// For inputs/textareas, "value" is a good proxy
	return strings.TrimSpace(attr(el, "value")) == ""
}

func isRequired(el *rod.Element) bool {
	if strings.EqualFold(attr(el, "aria-required"), "true") {
		return true
	}
	// presence of "required" attribute
	if v, _ := el.Attribute("required"); v != nil {
		return true
	}
	// sometimes class contains "required"
	if strings.Contains(strings.ToLower(attr(el, "class")), "required") {
		return true
	}
	return false
}

func click(el *rod.Element) error {
	_ = el.ScrollIntoView()
	// Prefer real click
	if err := el.Click(proto.InputMouseButtonLeft, 1); err == nil {
		return nil
	}
	// Fallback to JS click
	_, err := el.Eval(`(e) => e.click()`)
	return err
}

func clearAndType(el *rod.Element, text string) error {
	_ = el.ScrollIntoView()
	// Select-all then input
	if err := el.SelectAllText(); err != nil {
		// if SelectAllText fails, try JS clear
		_, _ = el.Eval(`(e) => { try { e.value = ""; } catch (_) {} }`)
	}
	return el.Input(text)
}

// -------------------- Label extraction --------------------

func getBestLabelText(page *rod.Element, el *rod.Element) string {
	// 1) label[for=id]
	id := attr(el, "id")
	if id != "" {
		lab, err := page.Timeout(300 * time.Millisecond).Element(`label[for="` + cssEscape(id) + `"]`)
		if err == nil && lab != nil {
			if t, _ := lab.Text(); strings.TrimSpace(t) != "" {
				return strings.TrimSpace(t)
			}
		}
	}

	// 2) aria-label
	if v := attr(el, "aria-label"); v != "" {
		return v
	}

	// 3) placeholder
	if v := attr(el, "placeholder"); v != "" {
		return v
	}

	// 4) aria-labelledby (one or more ids)
	if ids := attr(el, "aria-labelledby"); ids != "" {
		var parts []string
		for _, one := range strings.Fields(ids) {
			node, err := page.Timeout(300 * time.Millisecond).Element("#" + cssEscape(one))
			if err == nil && node != nil {
				if t, _ := node.Text(); strings.TrimSpace(t) != "" {
					parts = append(parts, strings.TrimSpace(t))
				}
			}
		}
		if len(parts) > 0 {
			return strings.Join(parts, " ")
		}
	}

	// 5) nearest fieldset/div text as fallback (JS: walk up and read innerText)
	j, err := el.Eval(`(e) => {
		let p = e;
		for (let i=0; i<4 && p; i++) {
			p = p.parentElement;
			if (!p) break;
			const tag = (p.tagName || "").toLowerCase();
			if (tag === "fieldset" || tag === "div") {
				const txt = (p.innerText || "").trim();
				if (txt) return txt.split("\n")[0].trim();
			}
		}
		return "";
	}`)
	if err == nil && j != nil {
		if s := j.Value.Str(); s != "" {
			return strings.TrimSpace(s)
		}
	}

	return ""
}

// Minimal CSS escaper for ids used inside attribute selectors.
func cssEscape(s string) string {
	// good enough for typical IDs; if you have weird chars, expand this.
	return strings.ReplaceAll(s, `"`, `\"`)
}

// -------------------- Heuristics --------------------

func ChooseValue(labelText, inputType string, p *store.LinkedInProfile, llmFallback func(label, typ string) (string, error)) string {
	l := strings.ToLower(strings.TrimSpace(labelText))
	t := strings.ToLower(strings.TrimSpace(inputType))

	containsAny := func(s string, kws ...string) bool {
		for _, kw := range kws {
			if strings.Contains(s, kw) {
				return true
			}
		}
		return false
	}

	switch {
	case containsAny(l, "phone", "mobile", "telephone", "contact"):
		return p.PhoneNumber
	case containsAny(l, "city", "location", "reside"):
		return p.UserCity + ", " + p.UserState
	case strings.Contains(l, "have you ever worked"):
		return "No"
	case strings.Contains(l, "state"):
		return p.UserState
	// case containsAny(l, "zip", "postal"):
	// 	return p.ZipCode TODO
	case containsAny(l, "salary", "wage", "income", "compensation"):
		return strconv.Itoa(p.DesiredSalary)
	case strings.Contains(l, "experience") && strings.Contains(l, "year"):
		return strconv.Itoa(p.YearsExperience)
	case containsAny(l, "linkedin", "linked-in", "linked in"):
		return p.ProfileURL
	}

	// defaults
	if t == "number" {
		return strconv.Itoa(p.YearsExperience)
	}

	if llmFallback != nil {
		if ans, err := llmFallback(labelText, inputType); err == nil && strings.TrimSpace(ans) != "" {
			return strings.TrimSpace(ans)
		}
	}

	return strconv.Itoa(p.YearsExperience)
}

// -------------------- Main: FillInvalids --------------------

func (bm *BrowserManager) FillInvalids(page *rod.Element, profile *store.LinkedInProfile, llmFallback func(label, typ string) (string, error)) error {
	const (
		textInputXPath = `//*[starts-with(@id, 'single-line-text-form-component-formElement-urn-li-jobs-applyformcommon-easyApplyFormElement-')]`
	)

	integerInputs := page.MustElementsX(textInputXPath)
	for _, inputEl := range integerInputs {
		if isEmpty(inputEl) && isRequired(inputEl) {
			labelText := getBestLabelText(page, inputEl)
			inputType := attr(inputEl, "type")
			value := ChooseValue(labelText, inputType, profile, llmFallback)
			if err := clearAndType(inputEl, value); err != nil {
				log.Printf("Failed to fill input for label '%s': %v", labelText, err)
			} else {
				log.Printf("Filled input for label '%s' with value '%s'", labelText, value)
			}
		}
	}

	return nil
}

func containsAny(s string, kws ...string) bool {
	for _, kw := range kws {
		if strings.Contains(s, kw) {
			return true
		}
	}
	return false
}

// Close shuts down the browser
func (bm *BrowserManager) Close() error {
	bm.mu.Lock()
	defer bm.mu.Unlock()

	if bm.browser == nil {
		return nil
	}

	err := bm.browser.Close()
	bm.browser = nil
	bm.SetApplying(false)
	bm.cancel()

	return err
}

// IsRunning checks if browser is currently running
func (bm *BrowserManager) IsRunning() bool {
	bm.mu.RLock()
	defer bm.mu.RUnlock()
	return bm.browser != nil
}

func (bm *BrowserManager) IsApplying() bool {
	// Check if the browser is currently applying
	return bm.ctx.Value("IsApplying") == true
}

func (bm *BrowserManager) SetApplying(value bool) {
	bm.ctx = context.WithValue(bm.ctx, "IsApplying", value)
}

// GetBrowser returns the rod browser instance
func (bm *BrowserManager) GetBrowser() *rod.Browser {
	bm.mu.RLock()
	defer bm.mu.RUnlock()
	return bm.browser
}

// NewPage creates a new browser page
func (bm *BrowserManager) NewPage() (*rod.Page, error) {
	bm.mu.RLock()
	defer bm.mu.RUnlock()

	if bm.browser == nil {
		return nil, fmt.Errorf("browser not running")
	}

	return bm.browser.MustPage(), nil
}

// Navigate opens a URL in a new page
func (bm *BrowserManager) Navigate(url string) (*rod.Page, error) {
	page, err := bm.NewPage()
	if err != nil {
		return nil, err
	}

	if err := page.Navigate(url); err != nil {
		return nil, fmt.Errorf("failed to navigate: %w", err)
	}

	return page, nil
}

// findBundledBrowser looks for a bundled browser in the app resources
func (bm *BrowserManager) findBundledBrowser() string {
	// Get executable directory
	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	exeDir := filepath.Dir(exe)

	var browserPath string
	switch runtime.GOOS {
	case "darwin":
		browserPath = filepath.Join(exeDir, "resources", "chrome", "Chromium.app", "Contents", "MacOS", "Chromium")
	case "windows":
		browserPath = filepath.Join(exeDir, "resources", "chrome", "chrome.exe")
	case "linux":
		browserPath = filepath.Join(exeDir, "resources", "chrome", "chrome")
	}

	if _, err := os.Stat(browserPath); err == nil {
		return browserPath
	}

	return ""
}

// findSystemBrowser looks for Chrome/Chromium installed on the system
func (bm *BrowserManager) findSystemBrowser() string {
	var paths []string

	switch runtime.GOOS {
	case "darwin":
		paths = []string{
			"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
			"/Applications/Chromium.app/Contents/MacOS/Chromium",
			"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
		}
	case "windows":
		paths = []string{
			`C:\Program Files\Google\Chrome\Application\chrome.exe`,
			`C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`,
			`C:\Program Files\Microsoft\Edge\Application\msedge.exe`,
		}
	case "linux":
		paths = []string{
			"/usr/bin/google-chrome",
			"/usr/bin/google-chrome-stable",
			"/usr/bin/chromium",
			"/usr/bin/chromium-browser",
		}
	}

	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	return ""
}

// Restart stops and starts the browser
func (bm *BrowserManager) Restart() error {
	if err := bm.Close(); err != nil {
		return err
	}
	err := bm.Launch()
	if err != nil {
		return err
	}
	return nil
}
