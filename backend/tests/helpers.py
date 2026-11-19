"""Shared assertions for the API tests."""


def assert_error(response, status, code=None, detail=None):
    """Asserts an error response's status (and optionally its code and detail); returns the body."""
    assert response.status_code == status, response.text
    body = response.json()
    if code is not None:
        assert body.get("code") == code, body
    if detail is not None:
        assert body["detail"] == detail, body
    return body
