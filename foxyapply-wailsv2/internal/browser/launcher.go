package browser

import (
	"applyfox/internal/store"
	"context"
	"errors"
	"fmt"
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
			fmt.Printf("⚪Applying to job ID: %d\n", jobID)
			page.MustNavigate(fmt.Sprintf("https://www.linkedin.com/jobs/view/%d", jobID))
			time.Sleep(2 * time.Second)
			_, err := bm.GetEasyApplyButton(page)
			if err != nil {
				fmt.Printf("❌No Easy Apply button for job ID %d: %v\n", jobID, err)
				continue
			}
			bm.FillOutEasyApplyForm(page, profile)
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
	res, err := page.Eval(`() => {
		const elements = Array.from(document.querySelectorAll('button[aria-label]'));
		const targetElement = elements.find(el => el.getAttribute('aria-label') && el.getAttribute('aria-label').includes('Easy Apply to'));
		if (targetElement) {
			targetElement.click();
			return true;
		}
		return false;
	}`)
	if err != nil {
		return false, err
	}
	return res.Value.Bool(), nil
}
func sleepRand(minSec, maxSec float64) {
	d := minSec + rand.Float64()*(maxSec-minSec)
	time.Sleep(time.Duration(d * float64(time.Second)))
}

func (bm *BrowserManager) FillOutEasyApplyForm(page *rod.Page, profile *store.LinkedInProfile) (bool, error) {
	// Locators (CSS) - mirrors your Python ones
	const (
		nextSel   = `button[aria-label='Continue to next step']`
		reviewSel = `button[aria-label='Review your application']`
		submitSel = `button[aria-label='Submit application']`
		// submitApplicationSel is the same selector in your python code
		submitApplicationSel = `button[aria-label='Submit application']`

		errorMessageSel = `.artdeco-inline-feedback__message`
		followLabelSel  = `label[for='follow-company-checkbox']`

		// has_errors(): XPath check
		errorIconXPath = `//*[contains(@type, "error-pebble-icon")]`
	)

	type locator struct {
		kind string // "css" or "xpath"
		q    string
	}

	buttons := []locator{
		{kind: "css", q: nextSel},
		{kind: "css", q: reviewSel},
		{kind: "css", q: followLabelSel},       // i == 2 special case
		{kind: "css", q: submitSel},            // i == 3 => submitted
		{kind: "css", q: submitApplicationSel}, // i == 4 => submitted
	}

	checkedInvalid := false
	submitted := false

	// --- helpers (close to your Python semantics) ---
	isPresent := func(loc locator) bool {
		// Fast existence check (no long wait)
		p := page.Timeout(300 * time.Millisecond)
		var el *rod.Element
		var err error
		if loc.kind == "xpath" {
			el, err = p.ElementX(loc.q)
		} else {
			el, err = p.Element(loc.q)
		}
		return err == nil && el != nil
	}

	hasErrors := func() bool {
		// Return true if any error icon exists
		return isPresent(locator{kind: "xpath", q: errorIconXPath})
	}

	handleInlineErrors := func() {
		// If error messages exist, scan their text for triggers
		if !isPresent(locator{kind: "css", q: errorMessageSel}) {
			return
		}

		els, err := page.Timeout(500 * time.Millisecond).Elements(errorMessageSel)
		if err != nil || len(els) == 0 {
			return
		}

		for _, el := range els {
			txt, err := el.Text()
			if err != nil {
				continue
			}
			if (strings.Contains(txt, "Please enter") ||
				strings.Contains(txt, "Please make") ||
				strings.Contains(txt, "Enter a") ||
				strings.Contains(txt, "Select checkbox to proceed")) && !checkedInvalid {

				if err := bm.FillInvalids(page, profile, nil); err != nil {
					log.Println("fillInvalids error:", err)
				}
				checkedInvalid = true
				break
			}
		}
	}

	clickWhenClickable := func(loc locator) error {
		var el *rod.Element
		var err error

		// Wait a bit for it to exist/appear
		p := page.Timeout(5 * time.Second)
		if loc.kind == "xpath" {
			el, err = p.ElementX(loc.q)
		} else {
			el, err = p.Element(loc.q)
		}
		if err != nil {
			return err
		}

		// Make sure it's interactable-ish:
		// - visible
		// - enabled (not disabled)
		if err := el.WaitVisible(); err != nil {
			return err
		}

		// Scroll into view then click
		_ = el.ScrollIntoView()
		return el.Click(proto.InputMouseButtonLeft, 1)
	}

	// --- main logic (port of your while True loop) ---
	defer func() {
		// match your final sleep in Python
		sleepRand(1.5, 2.5)
	}()

	sleepRand(1.5, 2.5)

	for i := 0; i < 15 && !submitted; i++ {
		// scan errors every loop like python does
		handleInlineErrors()

		var clickedIndex = -1

		for i, loc := range buttons {
			// python: if is_present(button_locator) and not has_errors():
			if isPresent(loc) && !hasErrors() {
				// wait until clickable + click
				if err := clickWhenClickable(loc); err == nil {
					clickedIndex = i
					sleepRand(1.5, 2.5)

					// python: if i in (3,4): submitted = True
					if i == 3 || i == 4 {
						submitted = true
					}

					// python: if i != 2: break (i==2 is follow checkbox; keep scanning)
					if i != 2 {
						break
					}
				}
			}

			handleInlineErrors()
		}

		if clickedIndex == -1 {
			time.Sleep(500 * time.Millisecond)
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

func getBestLabelText(page *rod.Page, el *rod.Element) string {
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

// -------------------- DOM-specific helpers --------------------

func HasInlineError(page *rod.Page) bool {
	// your python: XPath for error-pebble-icon
	_, err := page.Timeout(250 * time.Millisecond).ElementX(`//*[contains(@type, "error-pebble-icon")]`)
	return err == nil
}

func fieldsetHasError(fs *rod.Element) bool {
	_, err := fs.Timeout(250 * time.Millisecond).Element(".artdeco-inline-feedback__message")
	return err == nil
}

func selectByVisibleText(selectEl *rod.Element, text string) error {
	// JS approach: find option whose text matches, set value + dispatch change
	_, err := selectEl.Eval(`(sel, wanted) => {
		const opts = Array.from(sel.options || []);
		const target = opts.find(o => (o.textContent || "").trim() === wanted);
		if (!target) return false;
		sel.value = target.value;
		sel.dispatchEvent(new Event("change", { bubbles: true }));
		return true;
	}`, text)
	return err
}

// -------------------- Main: FillInvalids --------------------

func (bm *BrowserManager) FillInvalids(page *rod.Page, profile *store.LinkedInProfile, llmFallback func(label, typ string) (string, error)) error {
	// 1) GEO-LOCATION typeahead
	{
		locInput, err := page.Timeout(500 * time.Millisecond).Element(`input[id*="GEO-LOCATION"]`)
		if err == nil && locInput != nil && isEmpty(locInput) {
			_ = clearAndType(locInput, profile.UserCity+", "+profile.UserState)

			// wait for dropdown option and click it
			opt, err := page.Timeout(5 * time.Second).ElementX(
				`//div[contains(@class, 'basic-typeahead__selectable')]` +
					`//span[contains(@class, 'search-typeahead-v2__hit-text')]`,
			)
			if err == nil && opt != nil {
				_ = click(opt)
			}
		}
	}

	// 2) "Your Name" special case
	// {
	// 	lab, err := page.Timeout(500 * time.Millisecond).ElementX(`//label[contains(normalize-space(), 'Your Name')]`)
	// 	if err == nil && lab != nil {
	// 		forID := attr(lab, "for")
	// 		if forID != "" {
	// 			nameInput, err := page.Timeout(500 * time.Millisecond).Element("#" + cssEscape(forID))
	// 			if err == nil && nameInput != nil && isEmpty(nameInput) {
	// 				_ = clearAndType(nameInput, profile.)
	// 			}
	// 		}
	// 	}
	// }

	// 3) Inputs (required + empty OR page currently has errors)
	inputs, _ := page.Elements(`input.fb-dash-form-element`)
	for _, el := range inputs {
		inputType := strings.ToLower(attr(el, "type"))
		if inputType == "" {
			inputType = "text"
		}

		// skip non-fillables
		switch inputType {
		case "hidden", "submit", "button", "checkbox", "radio", "file":
			continue
		}

		if !(isRequired(el) || HasInlineError(page)) {
			continue
		}
		if !isEmpty(el) {
			continue
		}

		label := getBestLabelText(page, el)
		val := ChooseValue(label, inputType, profile, llmFallback)
		if strings.TrimSpace(val) == "" {
			continue
		}

		_ = clearAndType(el, val)
		sleepRand(0.2, 0.5)
	}

	// 4) Textareas
	textareas, _ := page.Elements(`textarea.fb-dash-form-element`)
	for _, el := range textareas {
		if !(isRequired(el) || HasInlineError(page)) {
			continue
		}
		if !isEmpty(el) {
			continue
		}
		label := getBestLabelText(page, el)
		val := ChooseValue(label, "text", profile, llmFallback)
		if strings.TrimSpace(val) == "" {
			continue
		}
		_ = clearAndType(el, val)
		sleepRand(0.2, 0.5)
	}

	// 5) Selects (required)
	selects, _ := page.Elements(`select[aria-required="true"], select[required]`)
	for _, sel := range selects {
		label := getBestLabelText(page, sel)
		q := strings.ToLower(label)

		// if already selected to something meaningful, skip
		cur, err := sel.Eval(`(e) => (e.options && e.selectedIndex >= 0) ? (e.options[e.selectedIndex].textContent || "").trim() : ""`)
		if err == nil && cur != nil {
			if curStr := cur.Value.Str(); curStr != "" {
				c := strings.ToLower(strings.TrimSpace(curStr))
				if c != "" && c != "select an option" && c != "please select" && c != "choose" && c != "-" {
					continue
				}
			}
		}

		// gather option texts
		optsJSON, err := sel.Eval(`(e) => Array.from(e.options || []).map(o => (o.textContent||"").trim())`)
		if err != nil || optsJSON == nil {
			continue
		}
		var opts []string
		for _, v := range optsJSON.Value.Arr() {
			if s := v.Str(); strings.TrimSpace(s) != "" {
				opts = append(opts, strings.TrimSpace(s))
			}
		}

		// heuristic pick
		chosen := ""
		for _, opt := range opts {
			ot := strings.ToLower(opt)
			if ot == "" || ot == "select an option" || ot == "please select" || ot == "choose" || ot == "-" {
				continue
			}

			if strings.Contains(ot, "united states") || ot == "us" || ot == "u.s." || ot == "usa" {
				chosen = opt
				break
			}
			if strings.Contains(q, "immediate family") && strings.Contains(ot, "no") {
				chosen = opt
				break
			}
			if (strings.Contains(q, "require") || strings.Contains(q, "sponsor") || strings.Contains(q, "visa")) && strings.Contains(ot, "no") {
				chosen = opt
				break
			}
			if (strings.Contains(q, "citizen") || strings.Contains(q, "work authorization")) && (strings.Contains(ot, "yes") || strings.Contains(ot, "authorized")) {
				chosen = opt
				break
			}
		}

		if chosen != "" {
			_ = selectByVisibleText(sel, chosen)
			sleepRand(0.1, 0.3)
		}
	}

	// 6) Radios inside invalid fieldsets
	fieldsets, _ := page.Elements("fieldset")
	for _, fs := range fieldsets {
		if !fieldsetHasError(fs) {
			continue
		}

		txt, _ := fs.Text()
		q := strings.TrimSpace(txt)
		if q == "" {
			continue
		}
		ql := strings.ToLower(q)

		// skip EEO demographic questions (optional + risky)
		if containsAny(ql, "gender", "race", "ethnicity", "veteran", "disability") {
			continue
		}

		yes, _ := fs.Elements(`input[data-test-text-selectable-option__input="Yes"]`)
		no, _ := fs.Elements(`input[data-test-text-selectable-option__input="No"]`)

		var target *rod.Element
		if containsAny(ql, "visa", "sponsor", "work authorization", "citizen") {
			if len(no) > 0 {
				target = no[0]
			}
		} else {
			// conservative default: "No" if available
			if len(no) > 0 {
				target = no[0]
			} else if len(yes) > 0 {
				target = yes[0]
			}
		}

		if target != nil {
			_ = click(target)
			sleepRand(0.1, 0.3)
		}
	}

	// settle
	time.Sleep(300 * time.Millisecond)

	// If the page still has errors, return an error so your caller can decide what to do.
	if HasInlineError(page) {
		return errors.New("form still has validation errors after FillInvalids")
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
