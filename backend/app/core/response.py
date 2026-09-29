from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    data: T | None = None
    message: str = "success"


def ok(data: Any = None, message: str = "success") -> dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "data": data, "message": message}
