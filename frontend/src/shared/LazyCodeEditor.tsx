import { lazy, Suspense } from 'react';
import type { CodeEditorProps } from './CodeEditor';

const CodeEditor = lazy(() => import('./CodeEditor'));

/**
 * S-32: CodeMirror грузится отдельным chunk'ом. До загрузки — обычный
 * textarea, поэтому ввод не блокируется и состояние не теряется.
 */
export function LazyCodeEditor(props: CodeEditorProps) {
  const {
    value,
    onChange,
    minHeight = 220,
    ariaLabel = 'Редактор Python',
  } = props;

  return (
    <Suspense
      fallback={
        <textarea
          className="editor"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          style={{ minHeight }}
          aria-label={ariaLabel}
        />
      }
    >
      <CodeEditor {...props} />
    </Suspense>
  );
}
