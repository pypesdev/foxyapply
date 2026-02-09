package pybot

import (
	"encoding/json"
	"testing"
)

func TestEventConstants(t *testing.T) {
	// Verify event constants match what the Python bot emits.
	expected := map[string]string{
		"EventLoginSuccess": "login_success",
		"EventLoginFailed":  "login_failed",
		"EventBotStarted":   "bot_started",
		"EventBotStopped":   "bot_stopped",
		"EventJobApplying":  "job_applying",
		"EventJobApplied":   "job_applied",
		"EventJobFailed":    "job_failed",
		"EventProgress":     "progress",
		"EventLog":          "log",
		"EventError":        "error",
	}

	actual := map[string]string{
		"EventLoginSuccess": EventLoginSuccess,
		"EventLoginFailed":  EventLoginFailed,
		"EventBotStarted":   EventBotStarted,
		"EventBotStopped":   EventBotStopped,
		"EventJobApplying":  EventJobApplying,
		"EventJobApplied":   EventJobApplied,
		"EventJobFailed":    EventJobFailed,
		"EventProgress":     EventProgress,
		"EventLog":          EventLog,
		"EventError":        EventError,
	}

	for name, want := range expected {
		got := actual[name]
		if got != want {
			t.Errorf("%s = %q, want %q", name, got, want)
		}
	}
}

func TestBotEventJSONRoundTrip(t *testing.T) {
	event := BotEvent{
		Type: EventJobApplied,
		Data: map[string]interface{}{
			"job_id":  "12345",
			"title":   "Software Engineer",
			"company": "Acme Corp",
		},
	}

	data, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded BotEvent
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.Type != event.Type {
		t.Errorf("Type = %q, want %q", decoded.Type, event.Type)
	}
	if decoded.Data["job_id"] != "12345" {
		t.Errorf("Data[job_id] = %v, want 12345", decoded.Data["job_id"])
	}
	if decoded.Data["company"] != "Acme Corp" {
		t.Errorf("Data[company] = %v, want Acme Corp", decoded.Data["company"])
	}
}

func TestBotEventUnmarshalFromPython(t *testing.T) {
	// Simulate the exact JSON the Python bot sends over WebSocket.
	raw := `{"type": "progress", "data": {"applied": 5, "failed": 1, "total_seen": 20}}`

	var event BotEvent
	if err := json.Unmarshal([]byte(raw), &event); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if event.Type != EventProgress {
		t.Errorf("Type = %q, want %q", event.Type, EventProgress)
	}

	// JSON numbers decode as float64 in map[string]interface{}
	applied, ok := event.Data["applied"].(float64)
	if !ok || applied != 5 {
		t.Errorf("Data[applied] = %v, want 5", event.Data["applied"])
	}
}

func TestBotEventEmptyData(t *testing.T) {
	raw := `{"type": "bot_started", "data": {}}`

	var event BotEvent
	if err := json.Unmarshal([]byte(raw), &event); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if event.Type != EventBotStarted {
		t.Errorf("Type = %q, want %q", event.Type, EventBotStarted)
	}
	if len(event.Data) != 0 {
		t.Errorf("Data should be empty, got %v", event.Data)
	}
}
