package automation

import (
	"github.com/go-rod/rod"
)

// Engine provides browser automation capabilities
type Engine struct {
	browser *rod.Browser
}

// NewEngine creates a new automation engine
func NewEngine(browser *rod.Browser) *Engine {
	return &Engine{browser: browser}
}
