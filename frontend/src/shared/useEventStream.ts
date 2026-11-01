import { useEffect, useRef, useState } from 'react';
import { API_BASE, getToken } from './api';

export type EventStreamStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error';

export interface EventStreamEvent {
  event: string;
  data: string;
  id: string | null;
}

export interface UseEventStreamOptions {
  /** Полный путь (/api/v1/...) или URL. null — поток не нужен. */
  url: string | null;
  enabled?: boolean;
  onEvent: (event: EventStreamEvent) => void;
  onError?: (error: Error) => void;
  maxRetries?: number;
  retryDelayMs?: number;
}

/** S-33: парсер одного SSE-блока (без зависимости от DOM). */
export function parseEventBlock(block: string): EventStreamEvent | null {
  let event = 'message';
  let id: string | null = null;
  const data: string[] = [];

  for (const rawLine of block.split('\n')) {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    if (!line || line.startsWith(':')) {
      continue;
    }
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) {
      value = value.slice(1);
    }
    if (field === 'event') {
      event = value;
    } else if (field === 'data') {
      data.push(value);
    } else if (field === 'id') {
      id = value;
    }
  }

  if (data.length === 0) {
    return null;
  }
  return { event, data: data.join('\n'), id };
}

function resolveUrl(url: string): string {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  return url.startsWith('/api/') ? url : `${API_BASE}${url}`;
}

/**
 * S-33: SSE через fetch (нужен Authorization Bearer, EventSource его не умеет).
 * При сетевой ошибке — reconnect с экспоненциальной задержкой и Last-Event-ID.
 */
export function useEventStream({
  url,
  enabled = true,
  onEvent,
  onError,
  maxRetries = 5,
  retryDelayMs = 1000,
}: UseEventStreamOptions): {
  status: EventStreamStatus;
  lastEventId: string | null;
} {
  const [status, setStatus] = useState<EventStreamStatus>('idle');
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const onEventRef = useRef(onEvent);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (!enabled || !url) {
      setStatus('idle');
      return;
    }

    let disposed = false;
    let controller: AbortController | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let retries = 0;
    let lastId: string | null = null;

    const connect = async (): Promise<void> => {
      if (disposed) {
        return;
      }
      controller = new AbortController();
      setStatus(retries > 0 ? 'reconnecting' : 'connecting');

      try {
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
        };
        const token = getToken();
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        if (lastId) {
          headers['Last-Event-ID'] = lastId;
        }

        const response = await fetch(resolveUrl(url), {
          headers,
          signal: controller.signal,
          credentials: 'include',
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(`SSE HTTP ${response.status}`);
        }
        if (!response.body) {
          throw new Error('SSE: пустой поток');
        }

        setStatus('open');
        retries = 0;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (!disposed) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
          let boundary = buffer.indexOf('\n\n');
          while (boundary >= 0) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const event = parseEventBlock(block);
            if (event) {
              if (event.id) {
                lastId = event.id;
                setLastEventId(event.id);
              }
              onEventRef.current(event);
            }
            boundary = buffer.indexOf('\n\n');
          }
        }

        if (!disposed) {
          setStatus('closed');
        }
      } catch (err) {
        if (
          disposed ||
          (err instanceof DOMException && err.name === 'AbortError')
        ) {
          return;
        }
        const error = err instanceof Error ? err : new Error(String(err));
        onErrorRef.current?.(error);
        if (retries < maxRetries) {
          retries += 1;
          setStatus('reconnecting');
          const delay = Math.min(retryDelayMs * 2 ** (retries - 1), 10000);
          retryTimer = setTimeout(() => {
            void connect();
          }, delay);
        } else {
          setStatus('error');
        }
      }
    };

    void connect();

    return () => {
      disposed = true;
      controller?.abort();
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
    };
  }, [url, enabled, maxRetries, retryDelayMs]);

  return { status, lastEventId };
}
