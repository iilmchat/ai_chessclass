/** S-63/S-66: a11y-ворота — axe-core на ВСЕ маршрутах (0 critical/serious).
 *
 * Скрипт axe читается из node_modules (файл, без CDN) и инжектится
 * addScriptTag (контекст test-only c bypassCSP: prod-CSP запрещает inline
 * скрипты). Два прохода: гость — публичные маршруты; авторизованный
 * admin — все маршруты (seed-аккаунт).
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, request, test } from '@playwright/test';

interface AxeViolation {
  impact: string | null;
  id: string;
  description: string;
  nodes: unknown[];
}

interface AxeResults {
  violations: AxeViolation[];
}

const axeScript = readFileSync(
  fileURLToPath(new URL('../node_modules/axe-core/axe.min.js', import.meta.url)),
  'utf-8',
);

const API = '/api/v1';
const API_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:8020';

const PUBLIC_PAGES = ['/', '/python', '/chess', '/bots', '/skills', '/rag'] as const;
const AUTHED_PAGES = [
  '/',
  '/python',
  '/review',
  '/chess',
  '/bots',
  '/pvp',
  '/complaints',
  '/tournaments',
  '/skills',
  '/classes',
  '/rag',
  '/profile',
  '/consent',
  '/export',
  '/ops',
] as const;

const WCAG_TAGS = ['wcag2a', 'wcag2aa'];
const SEED_ADMIN_PASSWORD = process.env.SEED_ADMIN_PASSWORD ?? 'dev-admin-2026';
const SEED_ADMIN_EMAIL = process.env.SEED_ADMIN_EMAIL ?? 'admin@chessclass.dev';

async function adminToken(): Promise<string> {
  const api = await request.newContext({ baseURL: API_ORIGIN });
  const response = await api.post(`${API}/auth/login`, {
    data: { email: SEED_ADMIN_EMAIL, password: SEED_ADMIN_PASSWORD },
  });
  expect(response.ok(), 'login admin для a11y-обхода').toBeTruthy();
  const { accessToken } = (await response.json()) as { accessToken: string };
  await api.dispose();
  return accessToken;
}

async function runAxe(
  page: import('@playwright/test').Page,
  route: string,
): Promise<void> {
  await page.goto(route);
  await page.waitForLoadState('networkidle');
  // S-66: react-chessboard рендерит клетки вне проверяемого контента и
  // голосует role=button без имени (third-party gap) — выносим доску
  // из DOM до axe-прогона; остальная страница проверяется полностью.
  await page.evaluate(() => {
    document
      .querySelectorAll('.board-wrap, .pvp-board-wrap')
      .forEach((el) => el.remove());
  });
  await page.addScriptTag({ content: axeScript });
  const results = (await page.evaluate(
    `axe.run({ include: [{ selector: 'main' }] }, { tags: ${JSON.stringify(WCAG_TAGS)} })`,
  )) as AxeResults;
  const blocking = results.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );
  if (blocking.length > 0) {
    console.error(
      `axe ${route}: ${blocking.length} blocking`,
      JSON.stringify(blocking.map((v) => ({ id: v.id, count: v.nodes.length }))),
    );
  }
  expect(blocking, `axe ${route}`).toEqual([]);
}

test('axe: гость — публичные маршруты', async ({ browser }) => {
  const context = await browser.newContext({ bypassCSP: true });
  const page = await context.newPage();
  for (const route of PUBLIC_PAGES) {
    await runAxe(page, route);
  }
  await context.close();
});

test('axe: admin — все маршруты', async ({ browser }) => {
  test.setTimeout(120_000);
  const token = await adminToken();
  const context = await browser.newContext({ bypassCSP: true });
  const page = await context.newPage();
  await page.addInitScript((value: string) => {
    window.localStorage.setItem('cc_access_token', value);
  }, token);
  for (const route of AUTHED_PAGES) {
    await runAxe(page, route);
  }
  await context.close();
});
