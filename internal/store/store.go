// Package store provides SQLite-based persistence for the application.
// Uses pure Go SQLite (no CGO) for cross-platform compatibility.
package store

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	_ "modernc.org/sqlite" // Pure Go SQLite driver
)

// Store handles all database operations
type Store struct {
	db *sql.DB
}

// New creates a new Store with SQLite database
func New() (*Store, error) {
	dbPath, err := getDBPath()
	if err != nil {
		return nil, fmt.Errorf("failed to get database path: %w", err)
	}

	// Ensure directory exists
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("failed to create data directory: %w", err)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Enable WAL mode for better concurrent access
	if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to enable WAL mode: %w", err)
	}

	// Enable foreign keys
	if _, err := db.Exec("PRAGMA foreign_keys=ON"); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to enable foreign keys: %w", err)
	}

	store := &Store{db: db}

	// Run migrations
	if err := store.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to run migrations: %w", err)
	}

	return store, nil
}

// NewWithPath creates a Store with a specific database path (useful for testing)
func NewWithPath(dbPath string) (*Store, error) {
	// Ensure directory exists
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("failed to create data directory: %w", err)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	store := &Store{db: db}

	if err := store.migrate(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to run migrations: %w", err)
	}

	return store, nil
}

// Close closes the database connection
func (s *Store) Close() error {
	return s.db.Close()
}

// DB returns the underlying database connection (for advanced queries)
func (s *Store) DB() *sql.DB {
	return s.db
}

// getDBPath returns the platform-specific database path
func getDBPath() (string, error) {
	var baseDir string

	switch runtime.GOOS {
	case "darwin":
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		baseDir = filepath.Join(home, "Library", "Application Support", "foxyapply")

	case "windows":
		appData := os.Getenv("APPDATA")
		if appData == "" {
			home, err := os.UserHomeDir()
			if err != nil {
				return "", err
			}
			appData = filepath.Join(home, "AppData", "Roaming")
		}
		baseDir = filepath.Join(appData, "foxyapply")

	default:
		configDir, err := os.UserConfigDir()
		if err != nil {
			home, err := os.UserHomeDir()
			if err != nil {
				return "", err
			}
			configDir = filepath.Join(home, ".config")
		}
		baseDir = filepath.Join(configDir, "foxyapply")
	}

	return filepath.Join(baseDir, "data.db"), nil
}

// migrate runs database migrations
func (s *Store) migrate() error {
	migrations := []string{
		// Migration 1: Create schema_version table
		`CREATE TABLE IF NOT EXISTS schema_version (
			version INTEGER PRIMARY KEY
		)`,

		// Migration 2: Create linkedin_profiles table

		`CREATE TABLE IF NOT EXISTS linkedin_profiles (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			email TEXT NOT NULL,
			password TEXT NOT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)`,

		// Migration 3: Add new columns to linkedin_profiles
		`ALTER TABLE linkedin_profiles ADD COLUMN phone_number TEXT DEFAULT ''`,
		`ALTER TABLE linkedin_profiles ADD COLUMN positions TEXT DEFAULT '[]'`,
		`ALTER TABLE linkedin_profiles ADD COLUMN locations TEXT DEFAULT '[]'`,
		`ALTER TABLE linkedin_profiles ADD COLUMN remote_only INTEGER DEFAULT 0`,
		`ALTER TABLE linkedin_profiles ADD COLUMN profile_url TEXT DEFAULT ''`,
		`ALTER TABLE linkedin_profiles ADD COLUMN years_experience INTEGER DEFAULT 0`,
		`ALTER TABLE linkedin_profiles ADD COLUMN user_city TEXT DEFAULT ''`,
		`ALTER TABLE linkedin_profiles ADD COLUMN user_state TEXT DEFAULT ''`,
	}

	for i, migration := range migrations {
		// Check if migration already applied
		var count int
		err := s.db.QueryRow("SELECT COUNT(*) FROM schema_version WHERE version = ?", i).Scan(&count)
		if err != nil && i > 0 {
			// Table might not exist for first migration
			return fmt.Errorf("migration %d failed: %w", i, err)
		}

		if count > 0 {
			continue // Already applied
		}

		// Apply migration
		if _, err := s.db.Exec(migration); err != nil {
			return fmt.Errorf("migration %d failed: %w", i, err)
		}

		// Record migration
		if _, err := s.db.Exec("INSERT INTO schema_version (version) VALUES (?)", i); err != nil {
			return fmt.Errorf("failed to record migration %d: %w", i, err)
		}
	}

	return nil
}

// GetDataDir returns the application data directory path
func GetDataDir() (string, error) {
	dbPath, err := getDBPath()
	if err != nil {
		return "", err
	}
	return filepath.Dir(dbPath), nil
}
