package store

import (
	"fmt"
	"time"
)

// JobApplication represents a single job application attempt
type JobApplication struct {
	ID           int64     `json:"id"`
	ProfileID    int64     `json:"profileId"`
	JobID        string    `json:"jobId"`
	Title        string    `json:"title"`
	Company      string    `json:"company"`
	Status       string    `json:"status"` // "applied" or "failed"
	ErrorMessage string    `json:"errorMessage"`
	AppliedAt    time.Time `json:"appliedAt"`
}

// ApplicationStats holds aggregate counts for job applications
type ApplicationStats struct {
	Applied int `json:"applied"`
	Failed  int `json:"failed"`
	Total   int `json:"total"`
}

// CreateJobApplication records a new job application
func (s *Store) CreateJobApplication(profileID int64, jobID, title, company, status, errorMessage string) (*JobApplication, error) {
	result, err := s.db.Exec(
		`INSERT INTO job_applications (profile_id, job_id, title, company, status, error_message)
		 VALUES (?, ?, ?, ?, ?, ?)`,
		profileID, jobID, title, company, status, errorMessage,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create job application: %w", err)
	}

	id, err := result.LastInsertId()
	if err != nil {
		return nil, fmt.Errorf("failed to get job application id: %w", err)
	}

	app := &JobApplication{}
	err = s.db.QueryRow(
		`SELECT id, profile_id, job_id, title, company, status, error_message, applied_at
		 FROM job_applications WHERE id = ?`, id,
	).Scan(&app.ID, &app.ProfileID, &app.JobID, &app.Title, &app.Company,
		&app.Status, &app.ErrorMessage, &app.AppliedAt)
	if err != nil {
		return nil, fmt.Errorf("failed to read back job application: %w", err)
	}

	return app, nil
}

// ListRecentApplications returns the most recent applications for a profile
func (s *Store) ListRecentApplications(profileID int64, limit int) ([]*JobApplication, error) {
	rows, err := s.db.Query(
		`SELECT id, profile_id, job_id, title, company, status, error_message, applied_at
		 FROM job_applications
		 WHERE profile_id = ?
		 ORDER BY applied_at DESC
		 LIMIT ?`,
		profileID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to list job applications: %w", err)
	}
	defer rows.Close()

	var apps []*JobApplication
	for rows.Next() {
		app := &JobApplication{}
		if err := rows.Scan(&app.ID, &app.ProfileID, &app.JobID, &app.Title, &app.Company,
			&app.Status, &app.ErrorMessage, &app.AppliedAt); err != nil {
			return nil, fmt.Errorf("failed to scan job application: %w", err)
		}
		apps = append(apps, app)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating job applications: %w", err)
	}

	return apps, nil
}

// GetApplicationStats returns aggregate counts for a profile's applications.
// If since is zero-valued, stats cover all time.
func (s *Store) GetApplicationStats(profileID int64, since time.Time) (*ApplicationStats, error) {
	var stats ApplicationStats

	query := `SELECT
		COALESCE(SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END), 0),
		COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0),
		COUNT(*)
	 FROM job_applications
	 WHERE profile_id = ?`

	var err error
	if since.IsZero() {
		err = s.db.QueryRow(query, profileID).Scan(&stats.Applied, &stats.Failed, &stats.Total)
	} else {
		query += ` AND applied_at >= ?`
		err = s.db.QueryRow(query, profileID, since).Scan(&stats.Applied, &stats.Failed, &stats.Total)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get application stats: %w", err)
	}

	return &stats, nil
}
