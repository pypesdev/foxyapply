package pybot

import (
	"bytes"
	"encoding/json"
	"fmt"
	"foxyapply/internal/store"
	"net/http"
	"time"
)

// ProfilePayload is the JSON body sent to POST /start on the Python bot.
// Field names use snake_case to match the Python Pydantic model.
type ProfilePayload struct {
	Email           string   `json:"email"`
	Password        string   `json:"password"`
	PhoneNumber     string   `json:"phone_number"`
	Positions       []string `json:"positions"`
	Locations       []string `json:"locations"`
	RemoteOnly      bool     `json:"remote_only"`
	ProfileURL      string   `json:"profile_url"`
	UserCity        string   `json:"user_city"`
	UserState       string   `json:"user_state"`
	ZipCode         string   `json:"zip_code"`
	YearsExperience int      `json:"years_experience"`
	DesiredSalary   int      `json:"desired_salary"`
	OpenAIAPIKey    string   `json:"openai_api_key"`
	Blacklist       []string `json:"blacklist"`
	BlacklistTitles []string `json:"blacklist_titles"`
}

// profileToPayload converts a store.LinkedInProfile to a ProfilePayload.
func profileToPayload(p *store.LinkedInProfile) *ProfilePayload {
	return &ProfilePayload{
		Email:           p.Email,
		Password:        p.Password,
		PhoneNumber:     p.PhoneNumber,
		Positions:       p.Positions,
		Locations:       p.Locations,
		RemoteOnly:      p.RemoteOnly,
		ProfileURL:      p.ProfileURL,
		UserCity:        p.UserCity,
		UserState:       p.UserState,
		ZipCode:         p.ZipCode,
		YearsExperience: p.YearsExperience,
		DesiredSalary:   p.DesiredSalary,
		Blacklist:       p.Blacklist,
		BlacklistTitles: p.BlacklistTitles,
	}
}

// postJSON sends a JSON POST request to the given URL.
func (m *Manager) postJSON(url string, payload interface{}) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal payload: %w", err)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("POST %s: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("POST %s returned %d", url, resp.StatusCode)
	}
	return nil
}

// getHealth checks if the Python bot's /health endpoint is reachable.
func (m *Manager) getHealth() error {
	url := fmt.Sprintf("http://127.0.0.1:%d/health", m.port)
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("health check returned %d", resp.StatusCode)
	}
	return nil
}
