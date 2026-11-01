import { Client } from 'pg';

const DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  'postgresql://chess:chess_dev_2026@127.0.0.1:5438/chessclass';

/** S-35: dev-email не отправляется по SMTP; токен берём из БД (e2e-стенд). */
export async function getVerifyToken(userId: string): Promise<string | null> {
  const client = new Client({ connectionString: DATABASE_URL });
  await client.connect();
  try {
    const result = await client.query<{ token: string }>(
      `select token from email_tokens
       where user_id = $1 and kind = 'verify' and used_at is null
       order by id desc limit 1`,
      [userId],
    );
    return result.rows[0]?.token ?? null;
  } finally {
    await client.end();
  }
}

export async function isEmailVerified(userId: string): Promise<boolean> {
  const client = new Client({ connectionString: DATABASE_URL });
  await client.connect();
  try {
    const result = await client.query<{ verified: boolean }>(
      `select (email_verified_at is not null) as verified
       from users where id = $1`,
      [userId],
    );
    return result.rows[0]?.verified ?? false;
  } finally {
    await client.end();
  }
}
