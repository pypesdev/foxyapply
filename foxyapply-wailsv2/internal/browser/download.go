package browser

import (
	"archive/zip"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// ChromeDownloader handles downloading Chrome for Testing
type ChromeDownloader struct {
	Version     string
	DownloadDir string
}

// ChromeForTestingURLs contains download URLs for each platform
var ChromeForTestingURLs = map[string]string{
	"darwin-arm64":  "https://storage.googleapis.com/chrome-for-testing-public/%s/mac-arm64/chrome-mac-arm64.zip",
	"darwin-amd64":  "https://storage.googleapis.com/chrome-for-testing-public/%s/mac-x64/chrome-mac-x64.zip",
	"linux-amd64":   "https://storage.googleapis.com/chrome-for-testing-public/%s/linux64/chrome-linux64.zip",
	"windows-amd64": "https://storage.googleapis.com/chrome-for-testing-public/%s/win64/chrome-win64.zip",
}

// LatestStableVersion is the Chrome for Testing version to use
// Update this when testing against new Chrome versions
const LatestStableVersion = "131.0.6778.85"

// NewChromeDownloader creates a downloader with default settings
func NewChromeDownloader() *ChromeDownloader {
	homeDir, _ := os.UserHomeDir()
	downloadDir := filepath.Join(homeDir, ".applyfox", "chrome")

	return &ChromeDownloader{
		Version:     LatestStableVersion,
		DownloadDir: downloadDir,
	}
}

// GetPlatformKey returns the current platform identifier
func GetPlatformKey() string {
	return fmt.Sprintf("%s-%s", runtime.GOOS, runtime.GOARCH)
}

// GetDownloadURL returns the download URL for the current platform
func (cd *ChromeDownloader) GetDownloadURL() (string, error) {
	platform := GetPlatformKey()
	urlTemplate, ok := ChromeForTestingURLs[platform]
	if !ok {
		return "", fmt.Errorf("unsupported platform: %s", platform)
	}
	return fmt.Sprintf(urlTemplate, cd.Version), nil
}

// GetBrowserPath returns the path to the downloaded browser executable
func (cd *ChromeDownloader) GetBrowserPath() string {
	platform := GetPlatformKey()
	versionDir := filepath.Join(cd.DownloadDir, cd.Version)

	switch {
	case strings.HasPrefix(platform, "darwin"):
		arch := "arm64"
		if strings.HasSuffix(platform, "amd64") {
			arch = "x64"
		}
		return filepath.Join(versionDir, fmt.Sprintf("chrome-mac-%s", arch), "Google Chrome for Testing.app", "Contents", "MacOS", "Google Chrome for Testing")
	case strings.HasPrefix(platform, "linux"):
		return filepath.Join(versionDir, "chrome-linux64", "chrome")
	case strings.HasPrefix(platform, "windows"):
		return filepath.Join(versionDir, "chrome-win64", "chrome.exe")
	}
	return ""
}

// IsDownloaded checks if Chrome is already downloaded
func (cd *ChromeDownloader) IsDownloaded() bool {
	path := cd.GetBrowserPath()
	if path == "" {
		return false
	}
	_, err := os.Stat(path)
	return err == nil
}

// Download downloads and extracts Chrome for Testing
func (cd *ChromeDownloader) Download(progressFn func(downloaded, total int64)) error {
	if cd.IsDownloaded() {
		return nil // Already downloaded
	}

	url, err := cd.GetDownloadURL()
	if err != nil {
		return err
	}

	// Create download directory
	versionDir := filepath.Join(cd.DownloadDir, cd.Version)
	if err := os.MkdirAll(versionDir, 0755); err != nil {
		return fmt.Errorf("failed to create download dir: %w", err)
	}

	// Download zip file
	zipPath := filepath.Join(versionDir, "chrome.zip")
	if err := cd.downloadFile(url, zipPath, progressFn); err != nil {
		return fmt.Errorf("failed to download: %w", err)
	}

	// Extract zip
	if err := cd.extractZip(zipPath, versionDir); err != nil {
		return fmt.Errorf("failed to extract: %w", err)
	}

	// Remove zip file
	os.Remove(zipPath)

	// Make executable on Unix
	if runtime.GOOS != "windows" {
		browserPath := cd.GetBrowserPath()
		if err := os.Chmod(browserPath, 0755); err != nil {
			return fmt.Errorf("failed to make executable: %w", err)
		}
	}

	return nil
}

// downloadFile downloads a file from URL to destination
func (cd *ChromeDownloader) downloadFile(url, dest string, progressFn func(downloaded, total int64)) error {
	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("bad status: %s", resp.Status)
	}

	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()

	if progressFn != nil {
		// Wrap with progress tracking
		reader := &progressReader{
			reader:     resp.Body,
			total:      resp.ContentLength,
			progressFn: progressFn,
		}
		_, err = io.Copy(out, reader)
	} else {
		_, err = io.Copy(out, resp.Body)
	}

	return err
}

// progressReader wraps an io.Reader to track progress
type progressReader struct {
	reader     io.Reader
	downloaded int64
	total      int64
	progressFn func(downloaded, total int64)
}

func (pr *progressReader) Read(p []byte) (int, error) {
	n, err := pr.reader.Read(p)
	pr.downloaded += int64(n)
	if pr.progressFn != nil {
		pr.progressFn(pr.downloaded, pr.total)
	}
	return n, err
}

// extractZip extracts a zip file to destination directory
func (cd *ChromeDownloader) extractZip(src, dest string) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		fpath := filepath.Join(dest, f.Name)

		// Check for zip slip vulnerability
		if !strings.HasPrefix(fpath, filepath.Clean(dest)+string(os.PathSeparator)) {
			return fmt.Errorf("invalid file path: %s", fpath)
		}

		if f.FileInfo().IsDir() {
			os.MkdirAll(fpath, os.ModePerm)
			continue
		}

		if err := os.MkdirAll(filepath.Dir(fpath), os.ModePerm); err != nil {
			return err
		}

		outFile, err := os.OpenFile(fpath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return err
		}

		rc, err := f.Open()
		if err != nil {
			outFile.Close()
			return err
		}

		_, err = io.Copy(outFile, rc)
		outFile.Close()
		rc.Close()

		if err != nil {
			return err
		}
	}

	return nil
}

// Cleanup removes downloaded browser files
func (cd *ChromeDownloader) Cleanup() error {
	return os.RemoveAll(cd.DownloadDir)
}
