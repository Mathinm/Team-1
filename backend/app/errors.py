"""Error format from SAD 4.4: {"error": {"code", "message", "details"}}.

Also turns FastAPI's default 422 validation errors into 400 (SAD 4.3: 400 = malformed data;
422 is reserved for business-rule failures such as INSUFFICIENT_STOCK).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_CODES = {
    400: "INVALID",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE",
    423: "LOCKED",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_response(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status, content=body)


def _field_message(err: dict) -> str:
    loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "header", "path")]
    field = loc[-1] if loc else "request"
    return f"{field}: {err.get('msg', 'invalid value')}"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        message = "; ".join(_field_message(e) for e in errors) or "Invalid request"
        details = [
            {"field": _field_message(e).split(":")[0], "message": e.get("msg")} for e in errors
        ]
        return error_response(400, "VALIDATION", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        code = _CODES.get(exc.status_code, str(exc.status_code))
        return error_response(exc.status_code, code, message)
