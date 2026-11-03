"""S-58: конфигурируемый CORS allowlist (CORS_ORIGINS)."""

from core.config import Settings

HEALTHZ = "/api/v1/healthz"


def _settings_with_cors(value: str) -> Settings:
    """Settings с сырым значением CORS_ORIGINS (валидатор mode='before')."""
    # mypy видит поле как list[str], но контракт: env/kwargs принимают строку.
    return Settings(_env_file=None, cors_origins=value)  # type: ignore[call-arg, arg-type]


def test_settings_parses_comma_separated_env() -> None:
    settings = _settings_with_cors("https://staging.example, http://localhost:3202")
    assert settings.cors_origins == ["https://staging.example", "http://localhost:3202"]

    settings = _settings_with_cors('["https://a","https://b"]')
    assert settings.cors_origins == ["https://a", "https://b"]

    settings = _settings_with_cors("")
    assert settings.cors_origins == []


async def test_cors_preflight_allows_configured_origin(make_client) -> None:
    client = await make_client()

    response = await client.options(
        HEALTHZ,
        headers={
            "Origin": "http://localhost:3200",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3200"

    # Нежданный origin: preflight отклоняется, ACAO в ответе нет.
    response = await client.options(
        HEALTHZ,
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

    # И обычный запрос с чужого origin не получает CORS-разрешения.
    response = await client.get(HEALTHZ, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
