// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VerifyEmailPage } from './VerifyEmailPage';

function renderPage(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <VerifyEmailPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('VerifyEmailPage', () => {
  it('shows success after a valid token is verified', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderPage('/verify-email?token=valid-token-1234567890');

    expect(screen.getByText('Проверяем токен…')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText('Email подтверждён, можно войти.')).toBeTruthy(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/verify',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ token: 'valid-token-1234567890' }),
      }),
    );
  });

  it('shows an error for an invalid token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'validation_error' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderPage('/verify-email?token=fake');

    await waitFor(() =>
      expect(screen.getByText(/Токен недействителен/)).toBeTruthy(),
    );
  });
});
