import { useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import { basicSetup } from 'codemirror';
import { indentUnit } from '@codemirror/language';
import { python } from '@codemirror/lang-python';
import { Compartment, EditorState } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';
import { EditorView } from '@codemirror/view';
import { usePrefersDark } from './usePrefersDark';

export interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  minHeight?: number;
  ariaLabel?: string;
}

const appTheme = EditorView.theme({
  '&': {
    backgroundColor: 'var(--panel)',
    color: 'var(--ink)',
    border: '1px solid var(--line)',
    borderRadius: '8px',
    overflow: 'hidden',
  },
  '&.cm-focused': {
    outline: '2px solid var(--accent)',
    outlineOffset: '1px',
  },
  '.cm-content': {
    fontFamily: "'Cascadia Code', Consolas, monospace",
    fontSize: '13px',
    lineHeight: '1.5',
    padding: '8px 0',
  },
  '.cm-gutters': {
    backgroundColor: 'var(--bg)',
    color: 'var(--muted)',
    borderRight: '1px solid var(--line)',
  },
  '.cm-activeLine': {
    backgroundColor: 'var(--accent-soft)',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'var(--accent-soft)',
  },
  '.cm-tooltip': {
    zIndex: '30',
  },
});

/** S-32: общий Python-редактор на CodeMirror 6 (лениво грузится из LazyCodeEditor). */
export default function CodeEditor({
  value,
  onChange,
  minHeight = 220,
  ariaLabel = 'Редактор Python',
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  const dark = usePrefersDark();
  const darkRef = useRef(dark);
  const themeCompartment = useRef(new Compartment()).current;

  valueRef.current = value;
  darkRef.current = dark;

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const parent = containerRef.current;
    if (!parent) {
      return;
    }

    const state = EditorState.create({
      doc: valueRef.current,
      extensions: [
        basicSetup,
        python(),
        indentUnit.of('    '),
        EditorState.tabSize.of(4),
        themeCompartment.of(darkRef.current ? oneDark : []),
        EditorView.contentAttributes.of({
          'aria-label': ariaLabel,
          spellcheck: 'false',
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current(update.state.doc.toString());
          }
        }),
        appTheme,
      ],
    });
    const view = new EditorView({ state, parent });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [ariaLabel, themeCompartment]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: themeCompartment.reconfigure(dark ? oneDark : []),
    });
  }, [dark, themeCompartment]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) {
      return;
    }
    const current = view.state.doc.toString();
    if (current !== value) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    }
  }, [value]);

  const style = {
    '--code-editor-min-height': `${minHeight}px`,
  } as CSSProperties;

  return (
    <div
      ref={containerRef}
      className="code-editor"
      style={style}
      data-testid="code-editor"
    />
  );
}
