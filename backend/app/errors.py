"""Application errors and the handlers that turn every failure into one JSON shape:

    {"error": {"code": "node_not_found", "message": "...", "details": [...]}}
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


# Validation failures are reported with the code of the field that failed.
_FIELD_CODES = {
    "name": "invalid_name",
    "type": "invalid_node_type",
    "bandwidth": "invalid_bandwidth",
    "latency": "invalid_latency",
    "packet_loss": "invalid_packet_loss",
    "node_count": "invalid_node_count",
    "source": "invalid_source",
    "destination": "invalid_destination",
    "template_name": "invalid_template",
    "packet_count": "invalid_packet_count",
    "packet_size": "invalid_packet_size",
    "random_seed": "invalid_random_seed",
    "store_packets": "invalid_store_packets",
    "recovery_id": "invalid_recovery_id",
    # Module 3: chaos injection
    "node_id": "invalid_node_id",
    "link_id": "invalid_link_id",
    "target_id": "invalid_target_id",
    "latency_increase": "invalid_latency_increase",
    "bandwidth_reduction_percent": "invalid_bandwidth_reduction",
    "scenario": "invalid_scenario",
    "experiment_name": "invalid_experiment_name",
    "description": "invalid_description",
    "events": "invalid_events",
    "parameters": "invalid_parameters",
}


def field_code(field: str) -> str:
    """Error code for a request field that failed validation."""
    return _FIELD_CODES.get(field, "validation_error")


def _error_response(status_code: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Spec asks for 400 (not FastAPI's default 422) on invalid input.
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
            for err in exc.errors()
        ]
        first_field = str(exc.errors()[0]["loc"][-1])
        code = field_code(first_field)
        first = details[0]
        return _error_response(400, code, f"{first['field']}: {first['message']}", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "internal_error", "Unexpected server error")
