import pytest

from scripts.serve_local_llm import DEFAULT_MODEL, build_command


def test_default_model_is_a_gemma_e4b_mlx_checkpoint():
    assert DEFAULT_MODEL == "mlx-community/gemma-4-e4b-it-4bit"


def test_vllm_command_is_bounded_and_uses_openai_server(tmp_path):
    executable = tmp_path / "vllm"
    executable.write_text("", encoding="utf-8")

    command = build_command(
        executable,
        "local-model",
        served_name="gemma",
        host="127.0.0.1",
        port=8001,
        max_model_len=8192,
    )

    assert command[:3] == [str(executable), "serve", "local-model"]
    assert command[command.index("--served-model-name") + 1] == "gemma"
    with pytest.raises(ValueError, match="port"):
        build_command(
            executable,
            "model",
            served_name="gemma",
            host="127.0.0.1",
            port=0,
            max_model_len=8192,
        )
