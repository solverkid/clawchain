package projector

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const finalRankingApplyPath = "/admin/poker-mtt/final-rankings/project"

type FinalRankingApplyClient struct {
	baseURL    string
	httpClient *http.Client
}

type ApplyResponse struct {
	StatusCode int
	Body       []byte
}

type ApplyError struct {
	StatusCode int
	Body       string
	Retryable  bool
}

func (e *ApplyError) Error() string {
	return fmt.Sprintf("poker mtt final ranking apply failed: status=%d retryable=%t body=%s", e.StatusCode, e.Retryable, e.Body)
}

func NewFinalRankingApplyClient(baseURL string, httpClient *http.Client) FinalRankingApplyClient {
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 10 * time.Second}
	}
	return FinalRankingApplyClient{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: httpClient,
	}
}

func (c FinalRankingApplyClient) Apply(ctx context.Context, payload FinalRankingApplyPayload) (ApplyResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return ApplyResponse{}, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+finalRankingApplyPath, bytes.NewReader(body))
	if err != nil {
		return ApplyResponse{}, err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.httpClient.Do(request)
	if err != nil {
		return ApplyResponse{}, &ApplyError{StatusCode: 0, Body: err.Error(), Retryable: true}
	}
	defer response.Body.Close()
	responseBody, readErr := io.ReadAll(response.Body)
	if readErr != nil {
		return ApplyResponse{}, readErr
	}
	result := ApplyResponse{StatusCode: response.StatusCode, Body: responseBody}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return result, &ApplyError{
			StatusCode: response.StatusCode,
			Body:       string(responseBody),
			Retryable:  retryableApplyStatus(response.StatusCode),
		}
	}
	return result, nil
}

func retryableApplyStatus(statusCode int) bool {
	return statusCode == http.StatusRequestTimeout || statusCode == http.StatusTooManyRequests || statusCode >= 500
}
