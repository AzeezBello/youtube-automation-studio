"""Local instruction-following LM adapter and deterministic template fallback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional

CompletionCallable = Callable[[str, Optional[str], int, float], str]


class TextGenerationAdapter(ABC):
    """Abstract interface for local text / instruction-following language models."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        ...


class LlamaCppTextAdapter(TextGenerationAdapter):
    """Local GGUF instruction-following LM adapter (llama-cpp-python or custom local completion callable)."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        *,
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        completion_fn: Optional[CompletionCallable] = None,
    ) -> None:
        self._model_path = model_path.expanduser().resolve() if model_path else None
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._completion_fn = completion_fn
        self._llm: Any = None

    @property
    def name(self) -> str:
        return "llama_cpp"

    def is_available(self) -> bool:
        if self._completion_fn is not None:
            return True
        if self._model_path is None or not self._model_path.exists():
            return False
        try:
            import llama_cpp  # noqa: F401

            return True
        except ImportError:
            return False

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        if self._completion_fn is not None:
            return self._completion_fn(prompt, system_prompt, max_tokens, temperature)

        if not self.is_available() or self._model_path is None:
            raise RuntimeError("LlamaCppTextAdapter is not available (missing model file or llama-cpp-python)")

        if self._llm is None:
            from llama_cpp import Llama

            kwargs: dict[str, Any] = {
                "model_path": str(self._model_path),
                "n_ctx": self._n_ctx,
                "verbose": False,
            }
            if self._n_threads:
                kwargs["n_threads"] = self._n_threads
            self._llm = Llama(**kwargs)

        sys_msg = system_prompt or "You are a helpful YouTube production assistant."
        formatted = f"<|system|>\n{sys_msg}\n<|user|>\n{prompt}\n<|assistant|>\n"
        out = self._llm(
            formatted,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|user|>", "<|system|>"],
        )
        choices = out.get("choices", [])
        if choices:
            return str(choices[0].get("text", "")).strip()
        return ""


class TemplateFallbackTextAdapter(TextGenerationAdapter):
    """Zero-dependency deterministic template adapter used when no local LLM is loaded."""

    @property
    def name(self) -> str:
        return "template_fallback"

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        first_line = next((ln.strip() for ln in prompt.splitlines() if ln.strip()), "Untitled Project")
        clean = first_line.replace("Project:", "").strip()
        return (
            f"{clean}\n\n"
            "Curated local-first music session prepared in YouTube Automation Studio."
        )
