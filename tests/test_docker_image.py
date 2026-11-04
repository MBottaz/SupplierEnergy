"""Contratto statico dell'immagine runtime Docker."""

from __future__ import annotations

from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DOCKERFILE = RADICE / "Dockerfile"
DOCKERIGNORE = RADICE / ".dockerignore"


def test_dockerfile_usa_lockfile_e_runtime_minimale() -> None:
    contenuto = DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM" in contenuto
    assert "uv sync --locked --no-dev --no-install-project" in contenuto
    assert "COPY pyproject.toml uv.lock" in contenuto
    assert "COPY etl" in contenuto
    assert "COPY offerte" in contenuto
    assert "COPY ." not in contenuto
    assert "USER offerte-mcp" in contenuto
    assert 'ENTRYPOINT ["python"]' in contenuto
    assert 'CMD ["-m", "offerte.mcp"]' in contenuto


def test_dockerignore_esclude_sorgenti_locali_e_tool_di_sviluppo() -> None:
    contenuto = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()

    for escluso in (".git", ".venv", "build/", "raw/", "tests/", "docs/"):
        assert escluso in contenuto
