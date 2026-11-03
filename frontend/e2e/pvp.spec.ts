/** S-65: PvP e2e — два браузера играют матч, жалоба закрывается в UI.
 *
 * Стек: seed-аккаунты (student1 student2 — участники, admin — ревьюер);
 * host создаёт комнату, гость входит по коду, обе страницы дожидаются
 * done (реальный SF-воркер в e2e-стеке), проверяют реплей.
 */

import { expect, request, test } from '@playwright/test';
import type { Browser, Page } from '@playwright/test';

const API_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:8020';
const API = '/api/v1';
const STUDENT1 = { email: 'student1@chessclass.dev', password: 'dev-student-2026' };
const STUDENT2 = { email: 'student2@chessclass.dev', password: 'dev-student-2026' };
const ADMIN = {
  email: process.env.SEED_ADMIN_EMAIL ?? 'admin@chessclass.dev',
  password: process.env.SEED_ADMIN_PASSWORD ?? 'dev-admin-2026',
};
const RANDOM_BOT =
  'import random\ndef choose_move(position):\n    return random.choice(position.legal_moves)\n';

test.describe.configure({ mode: 'serial' });

async function loginToken(api: import('@playwright/test').APIRequestContext, account: { email: string; password: string }): Promise<string> {
  const response = await api.post(`${API}/auth/login`, {
    data: { email: account.email, password: account.password },
  });
  expect(
    response.ok(),
    `login ${account.email}: HTTP ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  const { accessToken } = (await response.json()) as { accessToken: string };
  return accessToken;
}

async function makeBot(token: string): Promise<number> {
  const authed = await request.newContext({
    baseURL: API_ORIGIN,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const bot = await authed.post(`${API}/bots`, {
    data: { code: RANDOM_BOT, entry: 'choose_move' },
  });
  expect(bot.status()).toBe(201);
  const botBody = (await bot.json()) as { id: string };
  await authed.dispose();
  return Number(botBody.id);
}

async function asPage(browser: Browser, token: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addInitScript((value) => {
    window.localStorage.setItem('cc_access_token', value);
  }, token);
  return page;
}

test('PvP: два браузера играют матч, жалоба закрывается в UI', async ({ browser }) => {
  test.setTimeout(180_000);

  const boot = await request.newContext({ baseURL: API_ORIGIN });
  const hostToken = await loginToken(boot, STUDENT1);
  const guestToken = await loginToken(boot, STUDENT2);

  const [hostBotId] = await Promise.all([
    makeBot(hostToken),
    makeBot(guestToken),
  ]);
  void hostBotId;

  // host создаёт комнату (API), матч стартует из UI
  const room = await boot.post(`${API}/pvp/rooms`, {
    data: { botVersionId: hostBotId, rated: true },
    headers: { Authorization: `Bearer ${hostToken}` },
  });
  expect(room.status()).toBe(201);
  const code = ((await room.json()) as { code: string }).code;

  const pageHost = await asPage(browser, hostToken);
  await pageHost.goto('/pvp');
  await expect(
    pageHost.getByRole('heading', { name: 'PvP-матчи ботов' }),
  ).toBeVisible();

  const pageGuest = await asPage(browser, guestToken);
  await pageGuest.goto('/pvp');
  const codeBox = pageGuest.locator('input[placeholder="код комнаты гостя"]');
  await codeBox.fill(code);
  await pageGuest.getByRole('button', { name: 'Войти по коду' }).click();

  // обе страницы видят статус ready → running → done (реальный SF-воркер)
  await expect(pageHost.locator('.health-label').first()).toContainText('ready', {
    timeout: 30_000,
  });
  await expect(pageGuest.locator('.health-label').first()).toContainText('ready');

  await pageHost.getByRole('button', { name: /Запустить матч/ }).click();
  await expect(pageHost.locator('.health-label').first()).toContainText('done', {
    timeout: 150_000,
  });
  await expect(pageGuest.locator('.health-label').first()).toContainText('done');

  // реплей виден (доска + шаги по полуходам)
  await expect(pageHost.getByText(/Реплей · .+ · \d+ ходов/)).toBeVisible();
  await expect(pageGuest.getByText(/Реплей · .+ · \d+ ходов/)).toBeVisible();
  await pageGuest.getByRole('button', { name: /Шаг назад/ }).click();
  await expect(pageGuest.getByText(/полуход \d+\/\d+/)).toBeVisible();

  // жалоба host'а через UI
  await pageHost.locator('.pvp-complaint textarea').fill('подозрительные ходы');
  await pageHost.getByRole('button', { name: 'Отправить жалобу' }).click();
  await expect(pageHost.locator('.page-subtitle')).toContainText('жалоба отправлена', {
    timeout: 15_000,
  });

  // админ закрывает жалобу в UI: сначала переводим фильтр в «все статусы»,
  // иначе обновлённый список скроет строку (фильтр = open).
  const adminToken = await loginToken(boot, ADMIN);
  const pageAdmin = await asPage(browser, adminToken);
  await pageAdmin.goto('/complaints');
  const row = pageAdmin.locator('.pvp-complaint-row').first();
  await expect(row).toContainText('open', { timeout: 30_000 });
  await pageAdmin.getByLabel('Фильтр статуса').selectOption('');
  await row.locator('input.field').fill('проверено по SF-семплам');
  await row.getByRole('button', { name: /подтверждено/ }).click();
  // После ревью строка теряет класс .pvp-complaint-row (фильтр открытых) —
  // проверяем страницу в целом: статус reviewed + вердикт учителя виден.
  await expect(pageAdmin.locator('main')).toContainText('reviewed', {
    timeout: 15_000,
  });
  await expect(pageAdmin.locator('main')).toContainText('проверено по SF-семплам');

  await pageHost.context().close();
  await pageGuest.context().close();
  await pageAdmin.context().close();
});
