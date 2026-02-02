package store

import (
	"os"
	"path/filepath"
	"testing"
)

func setupTestStore(t *testing.T) (*Store, func()) {
	t.Helper()

	// Create temp directory for test database
	tmpDir, err := os.MkdirTemp("", "store-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}

	dbPath := filepath.Join(tmpDir, "test.db")
	store, err := NewWithPath(dbPath)
	if err != nil {
		os.RemoveAll(tmpDir)
		t.Fatalf("failed to create store: %v", err)
	}

	cleanup := func() {
		store.Close()
		os.RemoveAll(tmpDir)
	}

	return store, cleanup
}

func TestNewStore(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	if store == nil {
		t.Fatal("store should not be nil")
	}

	if store.DB() == nil {
		t.Fatal("database connection should not be nil")
	}
}
func TestLinkedInProfiles(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	// Test CreateLinkedInProfile
	profile, err := store.CreateLinkedInProfile("test@example.com", "password123")
	if err != nil {
		t.Fatalf("failed to create LinkedIn profile: %v", err)
	}

	if profile.Email != "test@example.com" {
		t.Errorf("expected email 'test@example.com', got '%s'", profile.Email)
	}

	if profile.Password != "password123" {
		t.Errorf("expected password 'password123', got '%s'", profile.Password)
	}

	// Test GetLinkedInProfile
	fetched, err := store.GetLinkedInProfile(profile.ID)
	if err != nil {
		t.Fatalf("failed to get LinkedIn profile: %v", err)
	}

	if fetched.ID != profile.ID {
		t.Errorf("expected ID %d, got %d", profile.ID, fetched.ID)
	}

	// Test UpdateLinkedInProfile
	updated, err := store.UpdateLinkedInProfile(profile.ID, LinkedInProfileUpdate{
		Email:           "test2@example.com",
		Password:        "newpassword",
		PhoneNumber:     "555-1234",
		Positions:       []string{"Software Engineer", "Backend Developer"},
		Locations:       []string{"San Francisco", "Remote"},
		RemoteOnly:      true,
		ProfileURL:      "https://linkedin.com/in/testuser",
		YearsExperience: 5,
		UserCity:        "San Francisco",
		UserState:       "CA",
	})
	if err != nil {
		t.Fatalf("failed to update LinkedIn profile: %v", err)
	}

	if updated.Email != "test2@example.com" {
		t.Errorf("expected email 'test2@example.com', got '%s'", updated.Email)
	}

	if updated.Password != "newpassword" {
		t.Errorf("expected password 'newpassword', got '%s'", updated.Password)
	}

	if updated.PhoneNumber != "555-1234" {
		t.Errorf("expected phone '555-1234', got '%s'", updated.PhoneNumber)
	}

	if len(updated.Positions) != 2 || updated.Positions[0] != "Software Engineer" {
		t.Errorf("expected positions to have 2 items, got %v", updated.Positions)
	}

	if !updated.RemoteOnly {
		t.Error("expected remoteOnly to be true")
	}

	if updated.YearsExperience != 5 {
		t.Errorf("expected yearsExperience 5, got %d", updated.YearsExperience)
	}

	// Test DeleteLinkedInProfile
	err = store.DeleteLinkedInProfile(profile.ID)
	if err != nil {
		t.Fatalf("failed to delete LinkedIn profile: %v", err)
	}

	_, err = store.GetLinkedInProfile(profile.ID)
	if err == nil {
		t.Error("expected error when getting deleted LinkedIn profile")
	}
}
