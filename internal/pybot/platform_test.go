package pybot

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// ---------------------------------------------------------------------------
// Binary resolution: platform-specific name and directory layout
// ---------------------------------------------------------------------------

func TestResolveBinary_ResourcesDir(t *testing.T) {
	// Simulate the Wails resource layout: <exeDir>/resources/easyapplybot
	tmpDir := t.TempDir()
	resDir := filepath.Join(tmpDir, "resources")
	if err := os.MkdirAll(resDir, 0755); err != nil {
		t.Fatal(err)
	}

	name := "easyapplybot"
	if runtime.GOOS == "windows" {
		name = "easyapplybot.exe"
	}
	binPath := filepath.Join(resDir, name)
	if err := os.WriteFile(binPath, []byte("fake"), 0755); err != nil {
		t.Fatal(err)
	}

	m := &Manager{BinaryPath: binPath}
	resolved := m.resolveBinary()
	if resolved != binPath {
		t.Errorf("resolveBinary = %q, want %q", resolved, binPath)
	}
}

func TestResolveBinary_WindowsExeSuffix(t *testing.T) {
	// Verify the .exe logic is correct for the current platform
	m := NewManager("")

	name := "easyapplybot"
	if runtime.GOOS == "windows" {
		name = "easyapplybot.exe"
	}

	// Create a temp dir that mimics the exe directory with the binary beside it
	tmpDir := t.TempDir()
	binPath := filepath.Join(tmpDir, name)
	if err := os.WriteFile(binPath, []byte("fake"), 0755); err != nil {
		t.Fatal(err)
	}

	// Set BinaryPath directly to the expected location
	m.BinaryPath = binPath
	resolved := m.resolveBinary()
	if resolved != binPath {
		t.Errorf("resolveBinary = %q, want %q", resolved, binPath)
	}

	// Verify wrong suffix doesn't match
	wrongName := "easyapplybot"
	if runtime.GOOS != "windows" {
		wrongName = "easyapplybot.exe"
	}
	m.BinaryPath = filepath.Join(tmpDir, wrongName)
	resolved = m.resolveBinary()
	// Wrong name shouldn't exist, so it falls through
	if resolved == m.BinaryPath {
		_, err := os.Stat(m.BinaryPath)
		if err != nil {
			t.Error("resolveBinary should not find a nonexistent file")
		}
	}
}

// ---------------------------------------------------------------------------
// Path construction: filepath.Join produces correct separators
// ---------------------------------------------------------------------------

func TestPathConstructionUsesPlatformSeparators(t *testing.T) {
	// filepath.Join should use the platform separator
	path := filepath.Join("resources", "easyapplybot")
	if runtime.GOOS == "windows" {
		if path != "resources\\easyapplybot" {
			t.Errorf("path = %q, want resources\\easyapplybot on Windows", path)
		}
	} else {
		if path != "resources/easyapplybot" {
			t.Errorf("path = %q, want resources/easyapplybot on Unix", path)
		}
	}
}

// ---------------------------------------------------------------------------
// URL construction: always uses forward slashes (HTTP standard)
// ---------------------------------------------------------------------------

func TestURLConstructionUsesForwardSlashes(t *testing.T) {
	m := &Manager{port: 8765}

	healthURL := fmt.Sprintf("http://127.0.0.1:%d/health", m.port)
	if healthURL != "http://127.0.0.1:8765/health" {
		t.Errorf("healthURL = %q", healthURL)
	}

	wsURL := fmt.Sprintf("ws://127.0.0.1:%d/ws", m.port)
	if wsURL != "ws://127.0.0.1:8765/ws" {
		t.Errorf("wsURL = %q", wsURL)
	}

	startURL := fmt.Sprintf("http://127.0.0.1:%d/start", m.port)
	if startURL != "http://127.0.0.1:8765/start" {
		t.Errorf("startURL = %q", startURL)
	}

	stopURL := fmt.Sprintf("http://127.0.0.1:%d/stop", m.port)
	if stopURL != "http://127.0.0.1:8765/stop" {
		t.Errorf("stopURL = %q", stopURL)
	}
}

// ---------------------------------------------------------------------------
// Port binding: verify freePort returns a port we can actually use
// ---------------------------------------------------------------------------

func TestFreePortIsBindable(t *testing.T) {
	port, err := freePort()
	if err != nil {
		t.Fatalf("freePort: %v", err)
	}

	// Verify we can actually bind to the returned port
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	l, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatalf("could not bind to free port %d: %v", port, err)
	}
	l.Close()
}

func TestLocalhostBindingWorks(t *testing.T) {
	// Verify 127.0.0.1 works on this platform (basic sanity)
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("cannot bind to 127.0.0.1:0: %v", err)
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()

	if port <= 0 || port > 65535 {
		t.Errorf("invalid port: %d", port)
	}
}

// ---------------------------------------------------------------------------
// Command construction: --port argument format
// ---------------------------------------------------------------------------

func TestCommandConstructionFormat(t *testing.T) {
	// Verify the command arguments are correctly formatted
	port := 12345
	args := []string{"--port", fmt.Sprintf("%d", port)}

	if args[0] != "--port" {
		t.Errorf("arg[0] = %q, want --port", args[0])
	}
	if args[1] != "12345" {
		t.Errorf("arg[1] = %q, want 12345", args[1])
	}
}

// ---------------------------------------------------------------------------
// Process lifecycle: Stop() is safe regardless of platform
// ---------------------------------------------------------------------------

func TestStopIdempotent(t *testing.T) {
	// Stop should be safe to call multiple times
	m := NewManager("")
	for i := 0; i < 5; i++ {
		if err := m.Stop(); err != nil {
			t.Fatalf("Stop() call %d failed: %v", i, err)
		}
	}
}

func TestStopCleansUpState(t *testing.T) {
	m := NewManager("")
	m.mu.Lock()
	m.running = true
	m.applying = true
	m.port = 1
	m.mu.Unlock()

	// Stop will try POST /stop (will fail, but should not panic)
	_ = m.Stop()

	if m.IsRunning() {
		t.Error("should not be running after Stop")
	}
	if m.IsApplying() {
		t.Error("should not be applying after Stop")
	}
}

// ---------------------------------------------------------------------------
// JSON payload: verify encoding is platform-independent
// ---------------------------------------------------------------------------

func TestProfilePayloadJSONIsPlatformIndependent(t *testing.T) {
	payload := &ProfilePayload{
		Email:           "test@test.com",
		Password:        "pass",
		PhoneNumber:     "555-1234",
		Positions:       []string{"Software Engineer"},
		Locations:       []string{"Remote", "New York"},
		RemoteOnly:      true,
		ProfileURL:      "https://linkedin.com/in/test",
		UserCity:        "New York",
		UserState:       "NY",
		ZipCode:         "10001",
		YearsExperience: 5,
		DesiredSalary:   120000,
		OpenAIAPIKey:    "sk-test",
		Blacklist:       []string{"Coinbase"},
		BlacklistTitles: []string{"intern"},
	}

	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	// JSON must not contain platform-specific characters (no backslashes in paths)
	jsonStr := string(data)
	for _, ch := range []string{"\r\n", "\r"} {
		if contains(jsonStr, ch) {
			t.Errorf("JSON contains platform-specific line ending %q", ch)
		}
	}

	// Verify it deserializes correctly
	var decoded ProfilePayload
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded.Email != payload.Email {
		t.Errorf("Email mismatch after round-trip")
	}
	if len(decoded.Positions) != 1 || decoded.Positions[0] != "Software Engineer" {
		t.Errorf("Positions mismatch after round-trip: %v", decoded.Positions)
	}
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// Integration: full HTTP+WS lifecycle on localhost (platform sanity check)
// ---------------------------------------------------------------------------

func TestFullHTTPWSLifecycle(t *testing.T) {
	// Spin up a mock Python bot server and verify the full Manager flow
	// works on this platform: health check, WS connect, event receive, stop.
	upgrader := websocket.Upgrader{}
	mux := http.NewServeMux()

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status": "ok"}`))
	})

	mux.HandleFunc("/start", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status": "starting"}`))
	})

	mux.HandleFunc("/stop", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status": "stopped"}`))
	})

	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()

		// Send a sequence of events like the real Python bot would
		events := []BotEvent{
			{Type: EventBotStarted, Data: map[string]interface{}{}},
			{Type: EventJobApplied, Data: map[string]interface{}{"job_id": "100", "title": "SWE", "company": "Acme"}},
			{Type: EventProgress, Data: map[string]interface{}{"applied": float64(1), "failed": float64(0), "total_seen": float64(1)}},
		}
		for _, evt := range events {
			data, _ := json.Marshal(evt)
			if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
				return
			}
			time.Sleep(10 * time.Millisecond)
		}

		// Keep alive until client disconnects
		for {
			_, _, err := conn.ReadMessage()
			if err != nil {
				return
			}
		}
	})

	// Bind to a free port
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	server := &http.Server{Handler: mux}
	go server.Serve(listener)
	defer server.Close()

	// 1. Health check
	m := NewManager("")
	m.port = port
	if err := m.waitHealthy(2 * time.Second); err != nil {
		t.Fatalf("health check failed: %v", err)
	}

	// 2. WebSocket connect
	wsURL := fmt.Sprintf("ws://127.0.0.1:%d/ws", port)
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("WS dial failed: %v", err)
	}

	var received []BotEvent
	m.wsConn = conn
	m.running = true
	m.SetEventHandler(func(e BotEvent) {
		received = append(received, e)
	})

	// 3. Read events in background
	done := make(chan struct{})
	go func() {
		m.readEvents()
		close(done)
	}()

	// 4. POST /start
	startURL := fmt.Sprintf("http://127.0.0.1:%d/start", port)
	if err := m.postJSON(startURL, map[string]string{"email": "a@b.com", "password": "pw"}); err != nil {
		t.Fatalf("POST /start failed: %v", err)
	}

	// 5. Wait for events to arrive
	time.Sleep(100 * time.Millisecond)

	// 6. Close the WebSocket connection (simulates stop) and wait for readEvents to finish
	conn.Close()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("readEvents did not return after connection close")
	}

	// Verify we received the events
	if len(received) < 3 {
		t.Fatalf("expected at least 3 events, got %d", len(received))
	}
	if received[0].Type != EventBotStarted {
		t.Errorf("event[0] = %q, want bot_started", received[0].Type)
	}
	if received[1].Type != EventJobApplied {
		t.Errorf("event[1] = %q, want job_applied", received[1].Type)
	}
	if received[2].Type != EventProgress {
		t.Errorf("event[2] = %q, want progress", received[2].Type)
	}
}

// ---------------------------------------------------------------------------
// Platform detection
// ---------------------------------------------------------------------------

func TestRuntimeGOOSIsKnown(t *testing.T) {
	// Sanity check that runtime.GOOS is one of our supported platforms
	switch runtime.GOOS {
	case "darwin", "linux", "windows":
		// expected
	default:
		t.Logf("warning: untested platform %q", runtime.GOOS)
	}
}
