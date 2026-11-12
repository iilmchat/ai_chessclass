"""v1.0.1: контракты production-деплоя (P0-1, P0-2, P1-1, P1-6)."""

from pathlib import Path

_MOUNT = Path("/repo")
ROOT = (
    _MOUNT
    if (_MOUNT / "docker-compose.prod.yml").is_file()
    else Path(__file__).resolve().parents[2]
)


def test_image_tag_matches_semver_without_v_prefix() -> None:
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    env_prod = (ROOT / ".env.prod.example").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "${IMAGE_TAG:-1.0.1}" in compose
    assert "IMAGE_TAG=1.0.1" in env_prod
    assert "docker/metadata-action@v5" in workflow
    assert "type=semver,pattern={{version}}" in workflow
    # Старый publish подставлял ref_name с префиксом v — регрессия P0-1.
    assert (
        "IMAGE_TAG: ${{ github.ref_type == 'tag' && github.ref_name || 'main' }}"
        not in workflow
    )


def test_env_file_reaches_containers() -> None:
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    env_prod = (ROOT / ".env.prod.example").read_text(encoding="utf-8")

    assert "x-env-file: &env-file" in compose
    assert "- path: ${ENV_FILE:-.env}" in compose
    assert "ENV_FILE=.env.prod" in env_prod
    # P0-2: env_file подключён ко всем backend-сервисам.
    assert compose.count("env_file: *env-file") >= 7


def test_web_binds_loopback_only() -> None:
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${WEB_PORT:-3200}:80"' in compose
    assert '"${WEB_PORT:-3200}:80"' not in compose


def test_alertmanager_starts_without_telegram() -> None:
    template = (
        ROOT / "deploy/observability/prod/alertmanager.yml.tmpl"
    ).read_text(encoding="utf-8")
    render = (
        ROOT / "deploy/observability/prod/alertmanager-render.sh"
    ).read_text(encoding="utf-8")

    assert "receiver: __DEFAULT_RECEIVER__" in template
    assert '- name: "null"' in template
    assert "# __TELEGRAM_BEGIN__" in template
    assert "telegram_enabled=0" in render
    assert 'default_receiver=\'"null"\'' in render
    # P1-6: пустой токен больше не валит рендер.
    assert ': "${TELEGRAM_BOT_TOKEN:?' not in render


def test_gitleaks_false_positives_allowlisted() -> None:
    ignore = (ROOT / ".gitleaksignore").read_text(encoding="utf-8")

    assert "generic-api-key:75" in ignore
    assert "telegram-bot-api-token:110" in ignore
