/** S-32: безопасные черновики редакторов в localStorage. */

const PREFIX = 'cc_draft';

export function draftKey(...parts: string[]): string {
  return [PREFIX, ...parts].join(':');
}

export function readDraft(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeDraft(key: string, value: string): void {
  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // Приватный режим/квота: черновик не критичен, редактор продолжает работать.
  }
}
