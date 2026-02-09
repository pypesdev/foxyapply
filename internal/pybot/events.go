package pybot

// BotEvent represents a real-time event received from the Python bot over WebSocket.
type BotEvent struct {
	Type string                 `json:"type"`
	Data map[string]interface{} `json:"data"`
}

// Event type constants matching the Python bot's WebSocket event names.
const (
	EventLoginSuccess = "login_success"
	EventLoginFailed  = "login_failed"
	EventBotStarted   = "bot_started"
	EventBotStopped   = "bot_stopped"
	EventJobApplying  = "job_applying"
	EventJobApplied   = "job_applied"
	EventJobFailed    = "job_failed"
	EventProgress     = "progress"
	EventLog          = "log"
	EventError        = "error"
)
