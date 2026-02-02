package store

import (
	"encoding/json"
	"fmt"
	"time"
)

// LinkedInProfile represents a user's LinkedIn profile
type LinkedInProfile struct {
	ID              int64     `json:"id"`
	Email           string    `json:"email"`
	Password        string    `json:"password"`
	PhoneNumber     string    `json:"phoneNumber"`
	Positions       []string  `json:"positions"`
	Locations       []string  `json:"locations"`
	RemoteOnly      bool      `json:"remoteOnly"`
	ProfileURL      string    `json:"profileUrl"`
	YearsExperience int       `json:"yearsExperience"`
	UserCity        string    `json:"userCity"`
	UserState       string    `json:"userState"`
	ZipCode         string    `json:"zipCode"`
	DesiredSalary   int       `json:"desiredSalary"`
	CreatedAt       time.Time `json:"createdAt"`
	UpdatedAt       time.Time `json:"updatedAt"`
}

// CreateLinkedInProfile creates a new LinkedIn profile
func (s *Store) CreateLinkedInProfile(email, password string) (*LinkedInProfile, error) {
	result, err := s.db.Exec(
		"INSERT INTO linkedin_profiles (email, password) VALUES (?, ?)",
		email, password,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create LinkedIn profile: %w", err)
	}

	id, err := result.LastInsertId()
	if err != nil {
		return nil, fmt.Errorf("failed to get LinkedIn profile id: %w", err)
	}

	return s.GetLinkedInProfile(id)
}

// GetLinkedInProfile retrieves a LinkedIn profile by ID
func (s *Store) GetLinkedInProfile(id int64) (*LinkedInProfile, error) {
	profile := &LinkedInProfile{}
	var positionsJSON, locationsJSON string
	var remoteOnly int

	err := s.db.QueryRow(
		`SELECT id, email, password, phone_number, positions, locations, remote_only,
		        profile_url, years_experience, user_city, user_state, created_at, updated_at
		 FROM linkedin_profiles WHERE id = ?`,
		id,
	).Scan(
		&profile.ID, &profile.Email, &profile.Password, &profile.PhoneNumber,
		&positionsJSON, &locationsJSON, &remoteOnly,
		&profile.ProfileURL, &profile.YearsExperience, &profile.UserCity, &profile.UserState,
		&profile.CreatedAt, &profile.UpdatedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get LinkedIn profile: %w", err)
	}

	// Parse JSON arrays
	if err := json.Unmarshal([]byte(positionsJSON), &profile.Positions); err != nil {
		profile.Positions = []string{}
	}
	if err := json.Unmarshal([]byte(locationsJSON), &profile.Locations); err != nil {
		profile.Locations = []string{}
	}
	profile.RemoteOnly = remoteOnly == 1

	return profile, nil
}

// ListLinkedInProfiles retrieves all LinkedIn profiles
func (s *Store) ListLinkedInProfiles() ([]*LinkedInProfile, error) {
	rows, err := s.db.Query(
		`SELECT id, email, password, phone_number, positions, locations, remote_only,
		        profile_url, years_experience, user_city, user_state, created_at, updated_at
		 FROM linkedin_profiles ORDER BY updated_at DESC`,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to list LinkedIn profiles: %w", err)
	}
	defer rows.Close()

	var profiles []*LinkedInProfile
	for rows.Next() {
		profile := &LinkedInProfile{}
		var positionsJSON, locationsJSON string
		var remoteOnly int

		if err := rows.Scan(
			&profile.ID, &profile.Email, &profile.Password, &profile.PhoneNumber,
			&positionsJSON, &locationsJSON, &remoteOnly,
			&profile.ProfileURL, &profile.YearsExperience, &profile.UserCity, &profile.UserState,
			&profile.CreatedAt, &profile.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan LinkedIn profile: %w", err)
		}

		// Parse JSON arrays
		if err := json.Unmarshal([]byte(positionsJSON), &profile.Positions); err != nil {
			profile.Positions = []string{}
		}
		if err := json.Unmarshal([]byte(locationsJSON), &profile.Locations); err != nil {
			profile.Locations = []string{}
		}
		profile.RemoteOnly = remoteOnly == 1

		profiles = append(profiles, profile)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating LinkedIn profiles: %w", err)
	}

	return profiles, nil
}

// LinkedInProfileUpdate contains fields that can be updated on a profile
type LinkedInProfileUpdate struct {
	Email           string   `json:"email"`
	Password        string   `json:"password"`
	PhoneNumber     string   `json:"phoneNumber"`
	Positions       []string `json:"positions"`
	Locations       []string `json:"locations"`
	RemoteOnly      bool     `json:"remoteOnly"`
	ProfileURL      string   `json:"profileUrl"`
	YearsExperience int      `json:"yearsExperience"`
	UserCity        string   `json:"userCity"`
	UserState       string   `json:"userState"`
}

// UpdateLinkedInProfile updates an existing LinkedIn profile
func (s *Store) UpdateLinkedInProfile(id int64, update LinkedInProfileUpdate) (*LinkedInProfile, error) {
	positionsJSON, err := json.Marshal(update.Positions)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal positions: %w", err)
	}
	locationsJSON, err := json.Marshal(update.Locations)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal locations: %w", err)
	}

	remoteOnly := 0
	if update.RemoteOnly {
		remoteOnly = 1
	}

	_, err = s.db.Exec(
		`UPDATE linkedin_profiles SET
			email = ?, password = ?, phone_number = ?, positions = ?, locations = ?,
			remote_only = ?, profile_url = ?, years_experience = ?, user_city = ?, user_state = ?,
			updated_at = CURRENT_TIMESTAMP
		 WHERE id = ?`,
		update.Email, update.Password, update.PhoneNumber, string(positionsJSON), string(locationsJSON),
		remoteOnly, update.ProfileURL, update.YearsExperience, update.UserCity, update.UserState, id,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to update LinkedIn profile: %w", err)
	}

	return s.GetLinkedInProfile(id)
}

// DeleteLinkedInProfile deletes a LinkedIn profile by ID
func (s *Store) DeleteLinkedInProfile(id int64) error {
	result, err := s.db.Exec("DELETE FROM linkedin_profiles WHERE id = ?", id)
	if err != nil {
		return fmt.Errorf("failed to delete LinkedIn profile: %w", err)
	}

	affected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get affected rows: %w", err)
	}

	if affected == 0 {
		return fmt.Errorf("LinkedIn profile not found: %d", id)
	}

	return nil
}
