package bot

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestOpenAIChatClientUsesChatCompletionsContract(t *testing.T) {
	var capturedPath string
	var capturedAuth string
	var capturedBody map[string]any

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedPath = r.URL.Path
		capturedAuth = r.Header.Get("Authorization")
		require.NoError(t, json.NewDecoder(r.Body).Decode(&capturedBody))
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"{\"action_type\":\"call\",\"amount\":0}"}}]}`))
	}))
	defer server.Close()

	client := NewOpenAIChatClient(OpenAIChatClientConfig{
		BaseURL: server.URL,
		APIKey:  "test-key",
		Model:   "gpt-5.4-mini",
	})

	out, err := client.Complete(context.Background(), "system prompt", "user prompt")
	require.NoError(t, err)
	require.Equal(t, "{\"action_type\":\"call\",\"amount\":0}", out)
	require.Equal(t, "/chat/completions", capturedPath)
	require.Equal(t, "Bearer test-key", capturedAuth)
	require.Equal(t, "gpt-5.4-mini", capturedBody["model"])

	messages := capturedBody["messages"].([]any)
	require.Len(t, messages, 2)
	require.Equal(t, "system", messages[0].(map[string]any)["role"])
	require.Equal(t, "user", messages[1].(map[string]any)["role"])
}
