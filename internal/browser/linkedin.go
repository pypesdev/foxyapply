package browser

import (
	"net/url"
	"strconv"
	"strings"
)

func ExtractJobID(href string) (int, bool) {
	parsedURL, err := url.Parse(href)
	if err != nil {
		return 0, false
	}

	segments := strings.Split(strings.Trim(parsedURL.Path, "/"), "/")
	if len(segments) < 2 {
		return 0, false
	}

	jobIDStr := segments[2]

	jobID, err := strconv.Atoi(jobIDStr)
	if err != nil {
		return 0, false
	}

	return jobID, true
}
