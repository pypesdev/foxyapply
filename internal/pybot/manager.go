package pybot

import (
	"encoding/json"
	"fmt"
	"foxyapply/internal/store"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Manager manages the lifecycle of the Python bot subprocess and its
// HTTP + WebSocket communication.
type Manager struct {
	mu       sync.RWMutex
	cmd      *exec.Cmd
	port     int
	running  bool
	applying bool

	wsConn  *websocket.Conn
	onEvent func(BotEvent)

	// Path to the bundled PyInstaller binary. When empty, the manager
	// will try to discover it relative to the running executable.
	BinaryPath string
}

// NewManager creates a new Manager. If binaryPath is empty, the manager will
// attempt to find the bundled bot binary in the resources directory.
func NewManager(binaryPath string) *Manager {
	return &Manager{
		BinaryPath: binaryPath,
	}
}

// SetEventHandler registers a callback invoked for every event received on
// the WebSocket from the Python bot.
func (m *Manager) SetEventHandler(fn func(BotEvent)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.onEvent = fn
}

// Start spawns the Python bot process, waits for it to become healthy, and
// connects the WebSocket for real-time events.
func (m *Manager) Start() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.running {
		return fmt.Errorf("bot already running")
	}

	// Pick a free port
	port, err := freePort()
	if err != nil {
		return fmt.Errorf("pick free port: %w", err)
	}
	m.port = port

	binPath := m.resolveBinary()
	if binPath == "" {
		return fmt.Errorf("could not find bot binary")
	}

	m.cmd = exec.Command(binPath, "--port", fmt.Sprintf("%d", m.port))
	m.cmd.Stdout = os.Stdout
	m.cmd.Stderr = os.Stderr

	if err := m.cmd.Start(); err != nil {
		return fmt.Errorf("start bot process: %w", err)
	}

	// Poll /health until ready (30s timeout — PyInstaller on macOS can be slow on first launch)
	if err := m.waitHealthy(30 * time.Second); err != nil {
		_ = m.kill()
		return fmt.Errorf("bot not healthy: %w", err)
	}

	// Connect WebSocket
	wsURL := fmt.Sprintf("ws://127.0.0.1:%d/ws", m.port)
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		_ = m.kill()
		return fmt.Errorf("connect websocket: %w", err)
	}
	m.wsConn = conn
	m.running = true

	// Start reading events in the background
	go m.readEvents()

	return nil
}

// StartApplying sends the profile data to the Python bot's POST /start
// endpoint to begin the application process.
func (m *Manager) StartApplying(profile *store.LinkedInProfile) error {
	m.mu.RLock()
	if !m.running {
		m.mu.RUnlock()
		return fmt.Errorf("bot not running")
	}
	m.mu.RUnlock()

	payload := profileToPayload(profile)
	url := fmt.Sprintf("http://127.0.0.1:%d/start", m.port)
	if err := m.postJSON(url, payload); err != nil {
		return fmt.Errorf("start applying: %w", err)
	}

	m.mu.Lock()
	m.applying = true
	m.mu.Unlock()
	return nil
}

// Stop gracefully stops the bot: POST /stop, close WebSocket, wait, force kill.
func (m *Manager) Stop() error {
	m.mu.Lock()
	if !m.running {
		m.applying = false
		m.mu.Unlock()
		return nil
	}
	port := m.port
	m.mu.Unlock()

	// Best-effort POST /stop
	stopURL := fmt.Sprintf("http://127.0.0.1:%d/stop", port)
	_ = m.postJSON(stopURL, nil)

	// Close WebSocket
	m.mu.Lock()
	if m.wsConn != nil {
		_ = m.wsConn.Close()
		m.wsConn = nil
	}
	m.mu.Unlock()

	// Wait up to 5s for process to exit
	done := make(chan error, 1)
	go func() {
		if m.cmd != nil && m.cmd.Process != nil {
			done <- m.cmd.Wait()
		} else {
			done <- nil
		}
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		_ = m.kill()
	}

	m.mu.Lock()
	m.running = false
	m.applying = false
	m.cmd = nil
	m.mu.Unlock()

	return nil
}

// IsRunning returns whether the bot process is running.
func (m *Manager) IsRunning() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.running
}

// IsApplying returns whether the bot is currently applying.
func (m *Manager) IsApplying() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.applying
}

// SetApplying sets the applying state.
func (m *Manager) SetApplying(v bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.applying = v
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

func (m *Manager) readEvents() {
	for {
		m.mu.RLock()
		conn := m.wsConn
		m.mu.RUnlock()
		if conn == nil {
			return
		}

		_, msg, err := conn.ReadMessage()
		if err != nil {
			// Connection closed or error — treat as bot stopped
			m.mu.Lock()
			wasRunning := m.running
			m.running = false
			m.applying = false
			m.mu.Unlock()

			if wasRunning {
				m.mu.RLock()
				handler := m.onEvent
				m.mu.RUnlock()
				if handler != nil {
					handler(BotEvent{
						Type: EventBotStopped,
						Data: map[string]interface{}{"reason": "connection lost"},
					})
				}
			}
			return
		}

		var event BotEvent
		if err := json.Unmarshal(msg, &event); err != nil {
			log.Printf("pybot: bad event JSON: %v", err)
			continue
		}

		// Update internal state based on events
		switch event.Type {
		case EventBotStarted:
			m.mu.Lock()
			m.applying = true
			m.mu.Unlock()
		case EventBotStopped:
			m.mu.Lock()
			m.applying = false
			m.mu.Unlock()
		}

		m.mu.RLock()
		handler := m.onEvent
		m.mu.RUnlock()
		if handler != nil {
			handler(event)
		}
	}
}

func (m *Manager) waitHealthy(timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if err := m.getHealth(); err == nil {
			return nil
		}
		time.Sleep(200 * time.Millisecond)
	}
	return fmt.Errorf("timeout waiting for bot to become healthy")
}

func (m *Manager) kill() error {
	if m.cmd != nil && m.cmd.Process != nil {
		return m.cmd.Process.Kill()
	}
	return nil
}

func (m *Manager) resolveBinary() string {
	if m.BinaryPath != "" {
		if _, err := os.Stat(m.BinaryPath); err == nil {
			return m.BinaryPath
		}
	}

	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	exeDir := filepath.Dir(exe)
	fmt.Printf("Looking for bot binary in %s\n", exeDir)
	name := "easyapplybot"
	if runtime.GOOS == "windows" {
		name = "easyapplybot.exe"
	}

	// Check resources/ next to the executable (standard Wails layout)
	candidate := filepath.Join(exeDir, "resources", name)
	if _, err := os.Stat(candidate); err == nil {
		return candidate
	}

	// Also check same directory as executable
	candidate = filepath.Join(exeDir, name)
	if _, err := os.Stat(candidate); err == nil {
		return candidate
	}

	return ""
}

func freePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	return port, nil
}
