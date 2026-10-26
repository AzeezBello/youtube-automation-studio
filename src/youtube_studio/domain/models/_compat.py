"""Pydantic BaseModel / Field compatibility layer with stdlib fallback when offline."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T", bound="BaseModel")

try:
    from pydantic import BaseModel as BaseModel  # type: ignore[assignment]
    from pydantic import Field as Field  # type: ignore[assignment]
except ImportError:

    class _FieldSpec:
        def __init__(
            self,
            default: Any = ...,
            *,
            default_factory: Callable[[], Any] | None = None,
        ) -> None:
            self.default = default
            self.default_factory = default_factory

    def Field(  # type: ignore[misc]
        default: Any = ...,
        *,
        default_factory: Callable[[], Any] | None = None,
        **_kwargs: Any,
    ) -> Any:
        return _FieldSpec(default, default_factory=default_factory)

    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            for cls in reversed(self.__class__.__mro__):
                if cls is object or cls is BaseModel:
                    continue
                annotations = getattr(cls, "__annotations__", {})
                for name in annotations:
                    if name in kwargs:
                        setattr(self, name, kwargs.pop(name))
                    elif hasattr(cls, name):
                        attr_val = getattr(cls, name)
                        if isinstance(attr_val, _FieldSpec):
                            if attr_val.default_factory is not None:
                                setattr(self, name, attr_val.default_factory())
                            else:
                                setattr(self, name, copy.deepcopy(attr_val.default))
                        elif not callable(attr_val) and not isinstance(attr_val, property):
                            setattr(self, name, copy.deepcopy(attr_val))
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> dict[str, Any]:
            def _serialize(val: Any) -> Any:
                if isinstance(val, BaseModel):
                    return val.model_dump()
                if isinstance(val, Enum):
                    return val.value
                if isinstance(val, datetime):
                    return val.isoformat()
                if isinstance(val, list):
                    return [_serialize(v) for v in val]
                if isinstance(val, dict):
                    return {k: _serialize(v) for k, v in val.items()}
                return val

            return {k: _serialize(v) for k, v in self.__dict__.items()}

        def model_dump_json(self) -> str:
            return json.dumps(self.model_dump())

        @classmethod
        def model_validate(cls: type[T], data: dict[str, Any] | T) -> T:
            if isinstance(data, cls):
                return data
            return cls(**dict(data))
