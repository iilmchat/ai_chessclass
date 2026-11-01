import { expect, request, test } from '@playwright/test';
import type { APIRequestContext, Page } from '@playwright/test';
import { getVerifyToken, isEmailVerified } from './db';

const API_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:8020';
const API = '/api/v1';
const PASSWORD = 'Passw0rd!123';
const ADMIN_EMAIL = process.env.SEED_ADMIN_EMAIL ?? 'admin@chessclass.dev';
const ADMIN_PASSWORD = process.env.SEED_ADMIN_PASSWORD ?? 'dev-admin-2026';

let api: APIRequestContext;
let email = '';
let userId = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  api = await request.newContext({ baseURL: API_ORIGIN });
});

test.afterAll(async () => {
  await api.dispose();
});

async function loginApi(): Promise<string> {
  const response = await api.post(`${API}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { accessToken: string };
  return body.accessToken;
}

async function authenticatePage(page: Page): Promise<void> {
  const token = await loginApi();
  await page.addInitScript((value) => {
    window.localStorage.setItem('cc_access_token', value);
  }, token);
}

test('1. регистрация student (API)', async ({}, testInfo) => {
  email = `e2e-${Date.now()}-${testInfo.retry}-${Math.random()
    .toString(16)
    .slice(2, 8)}@example.com`;

  const response = await api.post(`${API}/auth/register`, {
    data: { email, password: PASSWORD },
  });
  expect(response.status()).toBe(201);
  const body = (await response.json()) as { id: string; emailVerified: boolean };
  userId = body.id;
  expect(body.emailVerified).toBe(false);

  // До верификации вход запрещён.
  const login = await api.post(`${API}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(login.status()).toBe(403);
});

test('2. email verification + вход в UI', async ({ page }) => {
  const token = await getVerifyToken(userId);
  if (token) {
    const response = await api.post(`${API}/auth/verify`, {
      data: { token },
    });
    expect(response.ok()).toBeTruthy();
  } else {
    // Повтор после retry: токен уже использован.
    expect(await isEmailVerified(userId)).toBe(true);
  }

  await page.goto('/');
  await page.getByPlaceholder('email').fill(email);
  await page.getByPlaceholder('пароль').fill(PASSWORD);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByRole('button', { name: 'Выйти' })).toBeVisible();
  const stored = await page.evaluate(() =>
    window.localStorage.getItem('cc_access_token'),
  );
  expect(stored).toBeTruthy();
});

test.describe('authenticated journey', () => {
  test.beforeEach(async ({ page }) => {
    await authenticatePage(page);
  });

  test('3. задание: решение и вердикт passed', async ({ page }) => {
    await page.goto('/python');
    await page
      .getByRole('button', { name: /Приветствие \(переменные\)/ })
      .click();
    await expect(page.locator('.cm-editor')).toBeVisible();
    const editor = page.locator('.cm-content');
    await editor.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.insertText(
      'def greet(name):\n    return f"Привет, {name}!"\n',
    );
    await page.getByRole('button', { name: 'Проверить' }).click();
    await expect(page.locator('.verdict')).toContainText('Пройдено', {
      timeout: 20_000,
    });
  });

  test('4. инсайт позиции: факты SF + объяснение', async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto('/chess');
    await expect(page.locator('.board-wrap')).toBeVisible();
    await page.getByRole('button', { name: 'Получить инсайт' }).click();
    await expect(
      page.getByRole('heading', { name: 'Факты Stockfish (не выдуманы)' }),
    ).toBeVisible({ timeout: 75_000 });
    await expect(page.locator('.statement')).not.toHaveText('');
  });

  test('5. бот-матч: создание и SSE до результата', async ({ page }) => {
    await page.goto('/bots');
    await page.getByRole('button', { name: 'Сохранить версию' }).click();
    await expect(
      page.getByRole('button', { name: 'Матч vs random' }),
    ).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: 'Матч vs random' }).click();
    await expect(page.getByText(/Матч завершён/)).toBeVisible({
      timeout: 45_000,
    });
  });

  test('6. дашборд: здоровье и сводка', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.stats-grid')).toBeVisible();
    await expect(page.getByText('Инфраструктура')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Выйти' })).toBeVisible();
  });

  test('7. PDF родителям (API)', async () => {
    const admin = await request.newContext({ baseURL: API_ORIGIN });
    try {
      const login = await admin.post(`${API}/auth/login`, {
        data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
      });
      expect(login.ok()).toBeTruthy();
      const { accessToken } = (await login.json()) as { accessToken: string };
      const headers = { Authorization: `Bearer ${accessToken}` };

      const created = await admin.post(`${API}/reports/pdf/${userId}`, {
        headers,
      });
      expect(created.status()).toBe(201);
      const { reportId } = (await created.json()) as { reportId: number };

      const pdf = await admin.get(`${API}/reports/pdf/${reportId}`, {
        headers,
      });
      expect(pdf.ok()).toBeTruthy();
      expect(pdf.headers()['content-type']).toContain('application/pdf');
      const body = await pdf.body();
      expect(body.subarray(0, 4).toString()).toBe('%PDF');
    } finally {
      await admin.dispose();
    }
  });
});
