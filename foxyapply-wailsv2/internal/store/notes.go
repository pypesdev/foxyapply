package store

import (
	"fmt"
	"time"
)

// Note represents a simple note (hello world example entity)
type Note struct {
	ID        int64     `json:"id"`
	Title     string    `json:"title"`
	Content   string    `json:"content"`
	CreatedAt time.Time `json:"createdAt"`
	UpdatedAt time.Time `json:"updatedAt"`
}

// CreateNote creates a new note
func (s *Store) CreateNote(title, content string) (*Note, error) {
	result, err := s.db.Exec(
		"INSERT INTO notes (title, content) VALUES (?, ?)",
		title, content,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create note: %w", err)
	}

	id, err := result.LastInsertId()
	if err != nil {
		return nil, fmt.Errorf("failed to get note id: %w", err)
	}

	return s.GetNote(id)
}

// GetNote retrieves a note by ID
func (s *Store) GetNote(id int64) (*Note, error) {
	note := &Note{}
	err := s.db.QueryRow(
		"SELECT id, title, content, created_at, updated_at FROM notes WHERE id = ?",
		id,
	).Scan(&note.ID, &note.Title, &note.Content, &note.CreatedAt, &note.UpdatedAt)

	if err != nil {
		return nil, fmt.Errorf("failed to get note: %w", err)
	}

	return note, nil
}

// ListNotes retrieves all notes
func (s *Store) ListNotes() ([]*Note, error) {
	rows, err := s.db.Query(
		"SELECT id, title, content, created_at, updated_at FROM notes ORDER BY updated_at DESC",
	)
	if err != nil {
		return nil, fmt.Errorf("failed to list notes: %w", err)
	}
	defer rows.Close()

	var notes []*Note
	for rows.Next() {
		note := &Note{}
		if err := rows.Scan(&note.ID, &note.Title, &note.Content, &note.CreatedAt, &note.UpdatedAt); err != nil {
			return nil, fmt.Errorf("failed to scan note: %w", err)
		}
		notes = append(notes, note)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating notes: %w", err)
	}

	return notes, nil
}

// UpdateNote updates an existing note
func (s *Store) UpdateNote(id int64, title, content string) (*Note, error) {
	_, err := s.db.Exec(
		"UPDATE notes SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
		title, content, id,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to update note: %w", err)
	}

	return s.GetNote(id)
}

// DeleteNote deletes a note by ID
func (s *Store) DeleteNote(id int64) error {
	result, err := s.db.Exec("DELETE FROM notes WHERE id = ?", id)
	if err != nil {
		return fmt.Errorf("failed to delete note: %w", err)
	}

	affected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get affected rows: %w", err)
	}

	if affected == 0 {
		return fmt.Errorf("note not found: %d", id)
	}

	return nil
}
