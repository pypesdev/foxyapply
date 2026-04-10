.PHONY: all build dev clean install frontend backend darwin windows linux lint lint-fix test test-verbose test-coverage frontend-lint frontend-test frontend-check check check-all ci hooks-install help

# Default target
all: build

# Install dependencies
install:
	@echo "Installing Go dependencies..."
	go mod download
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Installing Wails CLI..."
	go install github.com/wailsapp/wails/v2/cmd/wails@latest
	@echo "Installing golangci-lint..."
	go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

# Install git hooks
hooks-install:
	@./.hooks/install.sh

# Development mode
dev:
	~/go/bin/wails dev

# Build for current platform
build: frontend
	~/go/bin/wails build

# Build frontend only
frontend:
	cd frontend && npm run build

# Build backend only
backend:
	go build -o build/bin/applyfox .

# Platform-specific builds
darwin:
	~/go/bin/wails build -platform darwin/universal

darwin-arm64:
	~/go/bin/wails build -platform darwin/arm64

darwin-amd64:
	~/go/bin/wails build -platform darwin/amd64

windows:
	~/go/bin/wails build -platform windows/amd64

linux:
	~/go/bin/wails build -platform linux/amd64

# Build all platforms
release: frontend
	@echo "Building for macOS (Universal)..."
	~/go/bin/wails build -platform darwin/universal -o applyfox-darwin-universal
	@echo "Building for Windows..."
	~/go/bin/wails build -platform windows/amd64 -o applyfox-windows-amd64.exe
	@echo "Building for Linux..."
	~/go/bin/wails build -platform linux/amd64 -o applyfox-linux-amd64

# Clean build artifacts
clean:
	rm -rf build/bin
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -f coverage.out coverage.html
	rm -rf frontend/coverage

# Generate Wails bindings
bindings:
	~/go/bin/wails generate module

# === Go Linting & Testing ===

# Run Go linter
lint:
	golangci-lint run

# Run Go linter with auto-fix
lint-fix:
	golangci-lint run --fix

# Run Go tests
test:
	go test ./...

# Run Go tests with verbose output
test-verbose:
	go test -v ./...

# Run Go tests with coverage
test-coverage:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

# === Frontend Linting & Testing ===

# Run frontend linter with auto-fix
frontend-lint:
	cd frontend && npm run lint

# Run frontend linter (check only)
frontend-lint-check:
	cd frontend && npm run lint:check

# Run frontend tests
frontend-test:
	cd frontend && npm run test:run

# Run frontend tests in watch mode
frontend-test-watch:
	cd frontend && npm run test

# Run frontend tests with coverage
frontend-test-coverage:
	cd frontend && npm run test:coverage

# Format frontend code
frontend-format:
	cd frontend && npm run format

# Check frontend formatting
frontend-format-check:
	cd frontend && npm run format:check

# Run all frontend checks
frontend-check:
	cd frontend && npm run check

# === Combined Commands ===

# Run all checks (lint + test for both Go and frontend)
check: lint test frontend-lint-check frontend-test
	@echo "All checks passed!"

# Run all checks with formatting
check-all: lint test frontend-check
	@echo "All checks passed!"

# CI pipeline command
ci: install check-all build
	@echo "CI pipeline completed successfully!"

# Tidy dependencies
tidy:
	go mod tidy
	cd frontend && npm audit fix || true

# Help
help:
	@echo "Available targets:"
	@echo ""
	@echo "Build & Run:"
	@echo "  install        - Install all dependencies (Go, npm, wails, golangci-lint)"
	@echo "  dev            - Run in development mode"
	@echo "  build          - Build for current platform"
	@echo "  frontend       - Build frontend only"
	@echo "  darwin         - Build for macOS (universal)"
	@echo "  windows        - Build for Windows"
	@echo "  linux          - Build for Linux"
	@echo "  release        - Build for all platforms"
	@echo "  clean          - Remove build artifacts"
	@echo ""
	@echo "Go Linting & Testing:"
	@echo "  lint           - Run Go linter"
	@echo "  lint-fix       - Run Go linter with auto-fix"
	@echo "  test           - Run Go tests"
	@echo "  test-verbose   - Run Go tests with verbose output"
	@echo "  test-coverage  - Run Go tests with coverage report"
	@echo ""
	@echo "Frontend Linting & Testing:"
	@echo "  frontend-lint       - Run frontend linter with auto-fix"
	@echo "  frontend-lint-check - Run frontend linter (check only)"
	@echo "  frontend-test       - Run frontend tests"
	@echo "  frontend-test-watch - Run frontend tests in watch mode"
	@echo "  frontend-test-coverage - Run frontend tests with coverage"
	@echo "  frontend-format     - Format frontend code"
	@echo "  frontend-check      - Run all frontend checks"
	@echo ""
	@echo "Combined:"
	@echo "  check          - Run lint and test for both Go and frontend"
	@echo "  check-all      - Run all checks including formatting"
	@echo "  ci             - Run full CI pipeline"
	@echo "  hooks-install  - Install git pre-commit hooks"
	@echo "  help           - Show this help"
