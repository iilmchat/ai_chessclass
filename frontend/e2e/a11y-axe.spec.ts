/** S-63: a11y-ворота — axe-core на основных маршрутах (0 critical/serious).
 *
 * Скрипт axe читается из node_modules (файл, без CDN) и инжектится
 * addScriptTag; CSP в dev/e2e не мешает (Vite dev-server). Полные правила
 * WCAG 2 A/AA получатся подтянуты к критериям S-66 (a11y-аудит).
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

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

const PAGES = ['/', '/python', '/chess', '/bots', '/skills'] as const;

const WCAG_TAGS = ['wcag2a', 'wcag2aa'];

test('axe: 0 critical/serious на публичных маршрутах', async ({ page }) => {
  for (const route of PAGES) {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    await page.addScriptTag({ content: axeScript });
    const results = (await page.evaluate(
      `axe.run(document, { tags: ${JSON.stringify(WCAG_TAGS)} })`,
    )) as AxeResults;

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    if (blocking.length > 0) {
      console.error(
        `axe ${route}: ${blocking.length} blocking violations`,
        JSON.stringify(
          blocking.map((v) => ({ id: v.id, nodes: v.nodes.length })),
          null,
          2,
        ),
      );
    }
    expect(blocking, `axe ${route}`).toEqual([]);
  }
});
