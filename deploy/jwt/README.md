# RS256-ключи JWT

Каталог для приватного/публичного PEM (S-47). **Не коммитить ключи.**

```powershell
.\scripts\gen-jwt-keys.ps1 -Force
```

Затем в `.env`:

```dotenv
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/srv/jwt/private.pem
JWT_PUBLIC_KEY_PATH=/srv/jwt/public.pem
JWT_KID=v1
JWT_LEGACY_HS256=false
```

S-90: legacy HS256 выключен по умолчанию. Включайте
`JWT_LEGACY_HS256=true` только на время миграции старых HS256-токенов;
в prod/staging оставляйте `false`.

В prod смонтируйте каталог в api (например, `./deploy/jwt:/srv/jwt:ro`) и
перезапустите api/worker. JWKS: `GET /api/v1/auth/jwks` и
`/.well-known/jwks.json`.
