import { useCallback, useEffect, useState } from 'react';
import { ApiError, speakText } from './api';

/** S-44: кнопка озвучки; при 503 текст остаётся, показываем мягкую ошибку. */
export function VoicePlayer({ text }: { text: string }) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const play = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const blob = await speakText(text);
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Озвучка временно недоступна',
      );
    } finally {
      setBusy(false);
    }
  }, [text]);

  return (
    <div className="voice-player">
      <button
        className="voice-button"
        type="button"
        disabled={busy || !text.trim()}
        onClick={play}
      >
        {busy ? 'Озвучиваем…' : '🔊 Озвучить'}
      </button>
      {audioUrl && <audio controls autoPlay src={audioUrl} />}
      {error && <span className="link-hint">{error}</span>}
    </div>
  );
}
