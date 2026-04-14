package authadapter

import (
	"context"
	"net/http"
)

func VerifyHTTPRequest(ctx context.Context, req *http.Request, verifier TokenVerifier) (Principal, error) {
	return HTTPVerifier{Verifier: verifier}.VerifyRequest(ctx, req)
}
