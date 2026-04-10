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

func TestCreateNote(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	note, err := store.CreateNote("Test Title", "Test Content")
	if err != nil {
		t.Fatalf("failed to create note: %v", err)
	}

	if note.ID == 0 {
		t.Error("note ID should not be 0")
	}

	if note.Title != "Test Title" {
		t.Errorf("expected title 'Test Title', got '%s'", note.Title)
	}

	if note.Content != "Test Content" {
		t.Errorf("expected content 'Test Content', got '%s'", note.Content)
	}

	if note.CreatedAt.IsZero() {
		t.Error("created_at should not be zero")
	}
}

func TestGetNote(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	created, err := store.CreateNote("Get Test", "Content")
	if err != nil {
		t.Fatalf("failed to create note: %v", err)
	}

	retrieved, err := store.GetNote(created.ID)
	if err != nil {
		t.Fatalf("failed to get note: %v", err)
	}

	if retrieved.ID != created.ID {
		t.Errorf("expected ID %d, got %d", created.ID, retrieved.ID)
	}

	if retrieved.Title != created.Title {
		t.Errorf("expected title '%s', got '%s'", created.Title, retrieved.Title)
	}
}

func TestGetNote_NotFound(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	_, err := store.GetNote(99999)
	if err == nil {
		t.Error("expected error for non-existent note")
	}
}

func TestListNotes(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	// Create multiple notes
	_, err := store.CreateNote("Note 1", "Content 1")
	if err != nil {
		t.Fatalf("failed to create note 1: %v", err)
	}

	_, err = store.CreateNote("Note 2", "Content 2")
	if err != nil {
		t.Fatalf("failed to create note 2: %v", err)
	}

	notes, err := store.ListNotes()
	if err != nil {
		t.Fatalf("failed to list notes: %v", err)
	}

	if len(notes) != 2 {
		t.Errorf("expected 2 notes, got %d", len(notes))
	}
}

func TestListNotes_Empty(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	notes, err := store.ListNotes()
	if err != nil {
		t.Fatalf("failed to list notes: %v", err)
	}

	if notes == nil {
		// nil is acceptable for empty list
		notes = []*Note{}
	}

	if len(notes) != 0 {
		t.Errorf("expected 0 notes, got %d", len(notes))
	}
}

func TestUpdateNote(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	created, err := store.CreateNote("Original", "Original Content")
	if err != nil {
		t.Fatalf("failed to create note: %v", err)
	}

	updated, err := store.UpdateNote(created.ID, "Updated", "Updated Content")
	if err != nil {
		t.Fatalf("failed to update note: %v", err)
	}

	if updated.Title != "Updated" {
		t.Errorf("expected title 'Updated', got '%s'", updated.Title)
	}

	if updated.Content != "Updated Content" {
		t.Errorf("expected content 'Updated Content', got '%s'", updated.Content)
	}

	if !updated.UpdatedAt.After(created.CreatedAt) && updated.UpdatedAt != created.CreatedAt {
		t.Error("updated_at should be >= created_at")
	}
}

func TestDeleteNote(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	created, err := store.CreateNote("To Delete", "Content")
	if err != nil {
		t.Fatalf("failed to create note: %v", err)
	}

	err = store.DeleteNote(created.ID)
	if err != nil {
		t.Fatalf("failed to delete note: %v", err)
	}

	_, err = store.GetNote(created.ID)
	if err == nil {
		t.Error("expected error when getting deleted note")
	}
}

func TestDeleteNote_NotFound(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	err := store.DeleteNote(99999)
	if err == nil {
		t.Error("expected error for non-existent note")
	}
}

func TestSettings(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	// Test SetSetting
	err := store.SetSetting("theme", "dark")
	if err != nil {
		t.Fatalf("failed to set setting: %v", err)
	}

	// Test GetSetting
	value, err := store.GetSetting("theme")
	if err != nil {
		t.Fatalf("failed to get setting: %v", err)
	}

	if value != "dark" {
		t.Errorf("expected 'dark', got '%s'", value)
	}

	// Test update (upsert)
	err = store.SetSetting("theme", "light")
	if err != nil {
		t.Fatalf("failed to update setting: %v", err)
	}

	value, err = store.GetSetting("theme")
	if err != nil {
		t.Fatalf("failed to get updated setting: %v", err)
	}

	if value != "light" {
		t.Errorf("expected 'light', got '%s'", value)
	}
}

func TestGetSetting_NotFound(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	value, err := store.GetSetting("nonexistent")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if value != "" {
		t.Errorf("expected empty string, got '%s'", value)
	}
}

func TestGetAllSettings(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	store.SetSetting("key1", "value1")
	store.SetSetting("key2", "value2")

	settings, err := store.GetAllSettings()
	if err != nil {
		t.Fatalf("failed to get all settings: %v", err)
	}

	if len(settings) != 2 {
		t.Errorf("expected 2 settings, got %d", len(settings))
	}

	if settings["key1"] != "value1" {
		t.Errorf("expected 'value1', got '%s'", settings["key1"])
	}
}

func TestDeleteSetting(t *testing.T) {
	store, cleanup := setupTestStore(t)
	defer cleanup()

	store.SetSetting("toDelete", "value")

	err := store.DeleteSetting("toDelete")
	if err != nil {
		t.Fatalf("failed to delete setting: %v", err)
	}

	value, _ := store.GetSetting("toDelete")
	if value != "" {
		t.Error("setting should be deleted")
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
