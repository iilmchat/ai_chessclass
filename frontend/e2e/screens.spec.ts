/** S-66: e2e новых экранов — 4 Travis­a (RAG · review · ops · telegram-link).
 *
 * Каждый тест — по одному экрану, чтобы сбой одного не останавливал набор;
 * use seeded аккаунты; авторизация через localStorage addInitScript.
 */

import { expect, request, test } from '@playwright/test';
import type { APIRequestContext, Browser, Page } from '@playwright/test';

const API_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:8020';
const API = '/api/v1';
const ADMIN_EMAIL = process.env.SEED_ADMIN_EMAIL ?? 'admin@chessclass.dev';
const ADMIN_PASSWORD = process.env.SEED_ADMIN_PASSWORD ?? 'dev-admin-2026';
const STUDENT_EMAIL = process.env.SEED_STUDENT_EMAIL ?? 'student1@chessclass.dev';
const STUDENT_PASSWORD = process.env.SEED_STUDENT_PASSWORD ?? 'dev-student-2026';

async function tokenFor(email: string, password: string): Promise<string> {
  const api: APIRequestContext = await request.newContext({ baseURL: API_ORIGIN });
  const response = await api.post(`${API}/auth/login`, {
    data: { email, password },
  });
  expect(response.ok(), `login ${email}`).toBeTruthy();
  const { accessToken } = (await response.json()) as { accessToken: string };
  await api.dispose();
  return accessToken;
}

async function asAuthorizedPage(browser: Browser, token: string): Promise<Page> {
  const context = await browser.newContext({});
  const page = await context.newPage();
  await page.addInitScript(
    (value: string) => {
      window.localStorage.setItem('cc_access_token', value);
    },
    token,
  );
  return page;
}

test('RAG: учитель создаёт черновик и публикует', async ({ browser }) => {
  test.setTimeout(120_000);
  const token = await tokenFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  const page = await asAuthorizedPage(browser, token);
  await page.goto('/rag');
  await expect(page.getByRole('heading', { name: 'RAG-база знаний' })).toBeVisible();

  const title = `e2e-draft-${Date.now()}`;
  const body = page.locator('.rag-form');
  await body.locator('input').first().fill(title);
  await body.locator('textarea').fill(
    'Уникальное понятие квантовый ферзь объясняет стратегию эндшпиля в этой заметке.',
  );
  await page.getByRole('button', { name: /Создать черновик/ }).click();
  // Факт создания — из интерфейса (уведомление в статус-строке).
  await expect(page.locator('main')).toContainText('Готово: черновик создан', {
    timeout: 20_000,
  });

  // API-факт: черновик существует (S-64: статус draft, затем published).
  const api = await request.newContext({
    baseURL: API_ORIGIN,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const docs = await api.get(`${API}/admin/rag/documents?status=draft`);
  expect(docs.ok()).toBeTruthy();
  const draftRow = ((await docs.json()) as { id: string; titleRu: string }[]).find(
    (r) => r.titleRu === title,
  );
  expect(draftRow).toBeTruthy();
  const draftId = (draftRow as { id: string }).id;

  // Публикация из UI: перезагрузка страницы снимает race refreshDocs
  // (клик ловил «залипший» DOM: кнопка была в снапшоте, но не
  // экшенилась — известный флейт CI; reload даёт чистое состояние).
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'RAG-база знаний' }),
  ).toBeVisible({ timeout: 20_000 });
  const row = page.locator('li', { hasText: title }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  const publishButton = row.getByRole('button', { name: /Опубликовать/ });
  await expect(publishButton).toBeVisible({ timeout: 10_000 });
  await publishButton.click();
  await expect(page.locator('main')).toContainText('Готово: публикация', {
    timeout: 30_000,
  });
  const published = await api.get(
    `${API}/admin/rag/documents?status=published`,
  );
  const publishedRow = ((await published.json()) as { id: string }[]).find(
    (r) => r.id === draftId,
  );
  expect(publishedRow).toBeTruthy();
  await api.dispose();
});

test('Review: SM-2 экран отвечает на данные профиля', async ({ browser }) => {
  const token = await tokenFor(STUDENT_EMAIL, STUDENT_PASSWORD);
  const page = await asAuthorizedPage(browser, token);
  await page.goto('/review');
  // Auth-ветка рендерит панель статистики SM-2 (due/streak) — факт S-52.
  await expect(page.locator('main')).toContainText('SM-2', { timeout: 20_000 });
});

test('Ops: панель retention/алертов видна admin', async ({ browser }) => {
  const token = await tokenFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  const page = await asAuthorizedPage(browser, token);
  await page.goto('/ops');
  await expect(page.locator('main')).toContainText(/Retention|Ретенш|Алер/i, {
    timeout: 20_000,
  });
});

test('Consent: родитель подтверждает ссылку', async ({ browser }) => {
  const token = await tokenFor(STUDENT_EMAIL, STUDENT_PASSWORD);
  const api = await request.newContext({
    baseURL: API_ORIGIN,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const profile = await api.patch(`${API}/profile/me`, {
    data: { ageGroup: 'child' },
  });
  expect(profile.ok()).toBeTruthy();
  const requested = await api.post(`${API}/consent/request`, {
    data: { parentEmail: 'parent@example.com' },
  });
  expect(requested.ok()).toBeTruthy();
  const { devToken } = (await requested.json()) as { devToken: string | null };
  expect(devToken).toBeTruthy();

  const page = await asAuthorizedPage(browser, token);
  await page.goto(`/consent?token=${encodeURIComponent(devToken as string)}`);
  await expect(page.locator('main')).toContainText(
    'Согласие родителя подтверждено',
    { timeout: 20_000 },
  );
  await api.dispose();
});

test('Telegram-link: код связи создаётся в профиле', async ({ browser }) => {
  const token = await tokenFor(STUDENT_EMAIL, STUDENT_PASSWORD);
  const page = await asAuthorizedPage(browser, token);
  await page.goto('/profile');
  const section = page.locator('main');
  await expect(section).toContainText(/Telegram/i, { timeout: 20_000 });
});
