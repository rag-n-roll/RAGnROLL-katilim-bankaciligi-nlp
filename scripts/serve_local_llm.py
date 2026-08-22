"""Gemma modelini Apple Silicon üzerinde vLLM-Metal ile servis eder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


DEFAULT_VLLM = Path(
    os.getenv(
        "RAGNROLL_VLLM_EXECUTABLE",
        str(Path.home() / ".venv-vllm-metal" / "bin" / "vllm"),
    )
)
DEFAULT_MODEL = os.getenv(
    "RAGNROLL_VLLM_MODEL_SOURCE",
    "mlx-community/gemma-4-e4b-it-4bit",
)


def build_command(
    executable: Path,
    model: str,
    *,
    served_name: str,
    host: str,
    port: int,
    max_model_len: int,
) -> list[str]:
    if not executable.is_file():
        raise FileNotFoundError(f"vLLM çalıştırıcısı bulunamadı: {executable}")
    if not 1 <= port <= 65535:
        raise ValueError("port 1 ile 65535 arasında olmalıdır")
    if not 1024 <= max_model_len <= 131072:
        raise ValueError("max_model_len 1024 ile 131072 arasında olmalıdır")
    return [
        str(executable),
        "serve",
        model,
        "--served-model-name",
        served_name,
        "--host",
        host,
        "--port",
        str(port),
        "--max-model-len",
        str(max_model_len),
        "--generation-config",
        "vllm",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm", type=Path, default=DEFAULT_VLLM)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="vLLM-Metal uyumlu yerel dizin veya Hugging Face model kimliği.",
    )
    parser.add_argument("--served-name", default="gemma4:e4b-mlx")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--max-model-len", type=int, default=8192)
    args = parser.parse_args()
    model_path = Path(args.model)
    model = str(model_path.resolve()) if model_path.exists() else args.model
    command = build_command(
        args.vllm,
        model,
        served_name=args.served_name,
        host=args.host,
        port=args.port,
        max_model_len=args.max_model_len,
    )
    os.execv(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
