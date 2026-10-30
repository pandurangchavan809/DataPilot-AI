"""Typed application errors mapped to HTTP responses."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        payload = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class ValidationError(AppError):
    code = "validation_error"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Please log in.", *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class NotConnectedError(AppError):
    status_code = 409
    code = "not_connected"

    def __init__(self, message: str = "No database connected for this session."):
        super().__init__(message)


class ConnectionFailedError(AppError):
    status_code = 422
    code = "connection_failed"


class UnsafeQueryError(AppError):
    status_code = 422
    code = "unsafe_query"


class QueryExecutionError(AppError):
    status_code = 422
    code = "query_failed"


class LLMError(AppError):
    status_code = 502
    code = "llm_error"
