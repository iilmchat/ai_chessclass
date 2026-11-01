// @vitest-environment jsdom
import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseEventBlock, useEventStream } from './useEventStream';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('parseEventBlock', () => {
  it('parses event/data/id', () => {
    expect(
      parseEventBlock('event: progress\ndata: {"status":"running"}\nid: 7'),
    ).toEqual({
      event: 'progress',
      data: '{"status":"running"}',
      id: '7',
    });
  });

  it('supports multi-line data and ignores comments', () => {
    expect(parseEventBlock(': keepalive\ndata: line1\ndata: line2')).toEqual({
      event: 'message',
      data: 'line1\nline2',
      id: null,
    });
  });

  it('returns null without data', () => {
    expect(parseEventBlock('event: ping')).toBeNull();
  });
});

describe('useEventStream', () => {
  it('reads SSE through fetch and calls onEvent', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: progress\ndata: {"status":"done"}\n\n'),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const onEvent = vi.fn();

    const { result } = renderHook(() =>
      useEventStream({
        url: '/api/v1/chess/games/1/events',
        onEvent,
        maxRetries: 0,
      }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1));
    expect(onEvent.mock.calls[0][0]).toMatchObject({
      event: 'progress',
      data: '{"status":"done"}',
    });
    await waitFor(() => expect(result.current.status).toBe('closed'));

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/chess/games/1/events',
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'text/event-stream',
        }),
      }),
    );
  });

  it('reconnects after a network error', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: progress\ndata: {"status":"running"}\n\n'),
        );
        controller.close();
      },
    });
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(
        new Response(stream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    const onEvent = vi.fn();

    renderHook(() =>
      useEventStream({
        url: '/api/v1/chess/games/2/events',
        onEvent,
        maxRetries: 1,
        retryDelayMs: 1,
      }),
    );

    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1), {
      timeout: 2000,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
