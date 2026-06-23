from enum import IntEnum
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(IntEnum):
    OK = 0
    VALIDATION_ERROR = 40001
    UNSUPPORTED_FILE_TYPE = 40002
    FILE_TOO_LARGE = 40003
    JOB_NOT_FOUND = 40401
    OUTPUT_NOT_FOUND = 40402
    INVALID_STATE = 40901
    SINGLE_JOB_BUSY = 40902
    INTERNAL_ERROR = 50001
    DOCLING_PARSE_FAILED = 50002
    LLM_CALL_FAILED = 50003


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.OK: "ok",
    ErrorCode.VALIDATION_ERROR: "参数校验失败",
    ErrorCode.UNSUPPORTED_FILE_TYPE: "文件类型不支持",
    ErrorCode.FILE_TOO_LARGE: "文件过大",
    ErrorCode.JOB_NOT_FOUND: "任务不存在",
    ErrorCode.OUTPUT_NOT_FOUND: "输出文件不存在",
    ErrorCode.INVALID_STATE: "当前状态不允许操作",
    ErrorCode.SINGLE_JOB_BUSY: "单任务队列忙",
    ErrorCode.INTERNAL_ERROR: "系统内部错误",
    ErrorCode.DOCLING_PARSE_FAILED: "Docling 解析失败",
    ErrorCode.LLM_CALL_FAILED: "LLM 调用失败",
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        data: Any = None,
        status_code: int = 400,
    ) -> None:
        self.code = code
        self.message = message or ERROR_MESSAGES[code]
        self.data = data
        self.status_code = status_code


def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": int(exc.code), "message": exc.message, "data": exc.data},
    )


def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": int(ErrorCode.VALIDATION_ERROR),
            "message": ERROR_MESSAGES[ErrorCode.VALIDATION_ERROR],
            "data": exc.errors(),
        },
    )


def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": int(ErrorCode.INTERNAL_ERROR),
            "message": ERROR_MESSAGES[ErrorCode.INTERNAL_ERROR],
            "data": None,
        },
    )
