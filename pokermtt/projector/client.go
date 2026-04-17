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
	baseURL      string
	httpClient   *http.Client
	bearerToken  string
	maxAttempts  int
	retryBackoff time.Duration
}

type FinalRankingApplyClientOptions struct {
	BearerToken  string
	MaxAttempts  int
	RetryBackoff time.Duration
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
	return NewFinalRankingApplyClientWithOptions(baseURL, httpClient, FinalRankingApplyClientOptions{MaxAttempts: 1})
}

func NewFinalRankingApplyClientWithOptions(baseURL string, httpClient *http.Client, options FinalRankingApplyClientOptions) FinalRankingApplyClient {
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 10 * time.Second}
	}
	maxAttempts := options.MaxAttempts
	if maxAttempts <= 0 {
		maxAttempts = 1
	}
	return FinalRankingApplyClient{
		baseURL:      strings.TrimRight(baseURL, "/"),
		httpClient:   httpClient,
		bearerToken:  options.BearerToken,
		maxAttempts:  maxAttempts,
		retryBackoff: options.RetryBackoff,
	}
}

func (c FinalRankingApplyClient) Apply(ctx context.Context, payload FinalRankingApplyPayload) (ApplyResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return ApplyResponse{}, err
	}

	for attempt := 1; attempt <= c.maxAttempts; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+finalRankingApplyPath, bytes.NewReader(body))
		if err != nil {
			return ApplyResponse{}, err
		}
		request.Header.Set("Content-Type", "application/json")
		if c.bearerToken != "" {
			request.Header.Set("Authorization", "Bearer "+c.bearerToken)
		}
		response, err := c.httpClient.Do(request)
		if err != nil {
			applyErr := &ApplyError{StatusCode: 0, Body: err.Error(), Retryable: true}
			if attempt < c.maxAttempts {
				c.sleepBeforeRetry(ctx)
				continue
			}
			return ApplyResponse{}, applyErr
		}
		responseBody, readErr := io.ReadAll(response.Body)
		closeErr := response.Body.Close()
		if readErr != nil {
			return ApplyResponse{}, readErr
		}
		if closeErr != nil {
			return ApplyResponse{}, closeErr
		}
		result := ApplyResponse{StatusCode: response.StatusCode, Body: responseBody}
		if response.StatusCode >= 200 && response.StatusCode < 300 {
			return result, nil
		}
		applyErr := &ApplyError{
			StatusCode: response.StatusCode,
			Body:       string(responseBody),
			Retryable:  retryableApplyStatus(response.StatusCode),
		}
		if applyErr.Retryable && attempt < c.maxAttempts {
			c.sleepBeforeRetry(ctx)
			continue
		}
		return result, applyErr
	}
	return ApplyResponse{}, &ApplyError{StatusCode: 0, Body: "retry attempts exhausted", Retryable: true}
}

func (c FinalRankingApplyClient) sleepBeforeRetry(ctx context.Context) {
	if c.retryBackoff <= 0 {
		return
	}
	timer := time.NewTimer(c.retryBackoff)
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}

func retryableApplyStatus(statusCode int) bool {
	return statusCode == http.StatusRequestTimeout || statusCode == http.StatusTooManyRequests || statusCode >= 500
}
