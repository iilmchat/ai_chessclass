import { useCallback, useEffect, useState } from 'react';
import type {
  RagDocDto,
  RagEvalDto,
  RagSearchDto,
  RagVersionDto,
} from '../shared/api';
import {
  ApiError,
  apiFetch,
  archiveRagDoc,
  createRagDoc,
  fetchRagDocs,
  fetchRagVersions,
  getToken,
  importRagDoc,
  logout,
  patchRagDoc,
  publishRagDoc,
  ragEval,
  ragSearch,
  rollbackRagDoc,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

interface DocForm {
  id: string | null;
  titleRu: string;
  domain: string;
  kind: string;
  license: string;
  source: string;
  text: string;
}

const EMPTY_FORM: DocForm = {
  id: null,
  titleRu: '',
  domain: 'general',
  kind: 'explanation',
  license: 'unknown',
  source: 'admin',
  text: '',
};

const STATUS_FILTERS = ['', 'draft', 'published', 'archived'];
const KINDS = ['explanation', 'teacher_solution', 'chess_position', 'hint'] as const;
const DOMAINS = ['python', 'chess', 'general'] as const;

/** S-64: RAG-база — список/редактор/версии/импорт/поиск/eval (teacher/admin). */
export function RagEditorPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [docList, setDocList] = useState<RagDocDto[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [form, setForm] = useState<DocForm>(EMPTY_FORM);
  const [versions, setVersions] = useState<{ docId: string; rows: RagVersionDto[] } | null>(null);
  const [search, setSearch] = useState<RagSearchDto | null>(null);
  const [evalReport, setEvalReport] = useState<RagEvalDto | null>(null);
  const [query, setQuery] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLicense, setImportLicense] = useState('unknown');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const isEditor = role === 'teacher' || role === 'admin';

  const refreshDocs = useCallback(
    (status: string) => {
      fetchRagDocs(status).then(setDocList).catch(() => setDocList([]));
    },
    [],
  );

  const load = useCallback(async () => {
    setError('');
    try {
      const profile = await apiFetch<{ role: string }>('/profile/me');
      setRole(profile.role);
      if (profile.role === 'teacher' || profile.role === 'admin') {
        const [docs, evalData] = await Promise.all([fetchRagDocs(''), ragEval()]);
        setDocList(docs);
        setEvalReport(evalData);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка RAG-базы');
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const act = useCallback(
    async (fn: () => Promise<void>, message: string) => {
      setBusy(message);
      setNotice('');
      setError('');
      try {
        await fn();
        setNotice(`Готово: ${message}`);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка операции');
      } finally {
        setBusy('');
      }
    },
    [],
  );

  const applyStatus = (status: string) => {
    setStatusFilter(status);
    refreshDocs(status);
  };

  const onSave = () =>
    act(
      async () => {
        const body = {
          titleRu: form.titleRu.trim(),
          domain: form.domain,
          kind: form.kind,
          license: form.license || 'unknown',
          text: form.text,
        };
        if (form.id) {
          await patchRagDoc(form.id, body);
        } else {
          await createRagDoc({ ...body, source: form.source || 'admin' });
        }
        refreshDocs(statusFilter);
        setForm(EMPTY_FORM);
      },
      form.id ? 'новая версия сохранена' : 'черновик создан',
    );

  const openVersions = (docId: string) =>
    act(async () => {
      setVersions({ docId, rows: await fetchRagVersions(docId) });
    }, 'история версий');

  const onRollback = (docId: string, version: number) =>
    act(async () => {
      await rollbackRagDoc(docId, version);
      setVersions(null);
      refreshDocs(statusFilter);
    }, `откат к версии ${version}`);

  const onImport = () => {
    if (!importFile) {
      setError('Выберите файл (.md/.txt/.pdf)');
      return;
    }
    act(
      async () => {
        const base64: string = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const value = String(reader.result ?? '');
            resolve(value.slice(value.indexOf(',') + 1));
          };
          reader.onerror = () => reject(new Error('файл не читается'));
          reader.readAsDataURL(importFile);
        });
        await importRagDoc({
          filename: importFile.name,
          contentBase64: base64,
          license: importLicense || 'unknown',
          domain: form.domain,
          kind: form.kind,
        });
        setImportFile(null);
        refreshDocs(statusFilter);
      },
      'импорт в черновик',
    );
  };

  const onSearch = () =>
    act(async () => {
      setSearch(await ragSearch(query.trim(), 5));
    }, 'поиск');

  const onEval = () =>
    act(async () => {
      setEvalReport(await ragEval());
    }, 'пересчёт eval');

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">RAG-база знаний</h1>
        <p className="page-subtitle" role="status" aria-live="polite">Редактура доступна после входа</p>
        <LoginGate hint="Панель учителя/админа" onReady={() => setAuthed(true)} />
      </section>
    );
  }
  if (!isEditor) {
    return (
      <section>
        <h1 className="page-title">RAG-база знаний</h1>
        <p className="verdict failed-note">
          Доступно учителю/админу (роль: {role || '—'})
        </p>
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">RAG-база знаний</h1>
      <p className="page-subtitle" role="status" aria-live="polite">
        Список / редактор / версии / импорт / поиск / eval (S-64) ·{' '}
        {busy || notice || '—'}
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}

      {/* --- Eval (gold-set) --- */}
      {evalReport && (
        <div className="panel rag-eval">
          <h2>
            Eval (gold-set {evalReport.cases}) · baseline {evalReport.baseline} · hybrid{' '}
            {evalReport.hybrid} ·{' '}
            <span className={evalReport.passed ? 'level-tag' : 'failed-note'}>
              {evalReport.passed ? 'hybrid ≥ baseline ✓' : 'hybrid < baseline ✗'}
            </span>
          </h2>
          <ul className="facts-list rag-eval-rows">
            {evalReport.results.map((row) => (
              <li key={row.order}>
                #{row.order} {row.query} · vector {row.vectorHit ? '✓' : '✗'} / hybrid{' '}
                {row.hybridHit ? '✓' : '✗'}
              </li>
            ))}
          </ul>
          <button className="retry-button" type="button" disabled={busy !== ''} onClick={onEval}>
            Пересчитать eval
          </button>
        </div>
      )}

      {/* --- Документы + редактор --- */}
      <div className="panel rag-docs">
        <div className="rag-toolbar">
          <h2>Документы ({docList.length})</h2>
          <select
            className="field"
            value={statusFilter}
            onChange={(e) => applyStatus(e.target.value)}
            aria-label="Фильтр статуса"
          >
            {STATUS_FILTERS.map((value) => (
              <option key={value || 'all'} value={value}>
                {value === '' ? 'все статусы' : value}
              </option>
            ))}
          </select>
        </div>
        <ul className="facts-list rag-doc-rows">
          {docList.map((doc) => (
            <li key={doc.id}>
              <strong>{doc.titleRu}</strong> · {doc.domain}/{doc.kind} · v{doc.version}{' '}
              <span className="level-tag">{doc.status}</span> · license {doc.license}{' '}
              <button
                className="retry-button"
                type="button"
                disabled={busy !== ''}
                onClick={() => openVersions(doc.id)}
              >
                Версии
              </button>
              {doc.status === 'draft' && (
                <button
                  className="retry-button"
                  type="button"
                  disabled={busy !== ''}
                  onClick={() =>
                    act(
                      async () => {
                        await publishRagDoc(doc.id);
                        refreshDocs(statusFilter);
                      },
                      `публикация «${doc.titleRu}»`,
                    )
                  }
                >
                  Опубликовать
                </button>
              )}
              {doc.status === 'published' && (
                <button
                  className="retry-button"
                  type="button"
                  disabled={busy !== ''}
                  onClick={() =>
                    act(
                      async () => {
                        await archiveRagDoc(doc.id);
                        refreshDocs(statusFilter);
                      },
                      `архив «${doc.titleRu}»`,
                    )
                  }
                >
                  В архив
                </button>
              )}
            </li>
          ))}
          {docList.length === 0 && (
            <li className="link-hint">Документов нет — создайте черновик ниже</li>
          )}
        </ul>

        {versions && (
          <div className="rag-versions">
            <h3>Версии документа #{versions.docId}</h3>
            <ul className="facts-list">
              {versions.rows.map((row) => (
                <li key={row.version}>
                  v{row.version} · license {row.license} · by {row.createdBy ?? '—'} ·{' '}
                  {row.createdAt.slice(0, 10)}
                  <button
                    className="retry-button"
                    type="button"
                    disabled={busy !== ''}
                    onClick={() =>
                      setForm({
                        id: versions.docId,
                        titleRu: row.titleRu,
                        domain: row.domain,
                        kind: row.kind,
                        license: row.license,
                        source: row.source,
                        text: row.text,
                      })
                    }
                  >
                    В редактор
                  </button>
                  <button
                    className="retry-button"
                    type="button"
                    disabled={busy !== ''}
                    onClick={() => onRollback(versions.docId, row.version)}
                  >
                    Откатить
                  </button>
                </li>
              ))}
            </ul>
            <button className="retry-button" type="button" onClick={() => setVersions(null)}>
              Скрыть версии
            </button>
          </div>
        )}

        <h3>
          Редактор{form.id ? ' (правка → новая версия)' : ' (новый черновик)'}
        </h3>
        <div className="rag-form">
          <input
            className="field"
            value={form.titleRu}
            placeholder="Заголовок (ru)"
            onChange={(e) => setForm({ ...form, titleRu: e.target.value })}
          />
          <select
            className="field"
            value={form.domain}
            onChange={(e) => setForm({ ...form, domain: e.target.value })}
            aria-label="Домен"
          >
            {DOMAINS.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <select
            className="field"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            aria-label="Тип"
          >
            {KINDS.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <input
            className="field"
            value={form.license}
            placeholder="license"
            onChange={(e) => setForm({ ...form, license: e.target.value })}
          />
          <textarea
            className="field rag-textarea"
            rows={6}
            value={form.text}
            placeholder="Текст материала (ru, ≥ 20 символов)"
            onChange={(e) => setForm({ ...form, text: e.target.value })}
          />
          <div className="submit-row">
            <button
              className="retry-button"
              type="button"
              disabled={
                busy !== '' ||
                form.text.trim().length < 20 ||
                form.titleRu.trim().length < 3
              }
              onClick={onSave}
            >
              {form.id ? 'Сохранить как новую версию' : 'Создать черновик'}
            </button>
            {form.id && (
              <button
                type="button"
                className="link-button"
                onClick={() => setForm(EMPTY_FORM)}
              >
                отмена правки
              </button>
            )}
          </div>
        </div>
      </div>

      {/* --- Импорт --- */}
      <div className="panel">
        <h2>Импорт (.md/.markdown/.txt/.pdf)</h2>
        <input
          type="file"
          aria-label="Файл для импорта"
          className="field"
          accept=".md,.markdown,.txt,.pdf"
          onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
        />
        <input
          className="field"
          value={importLicense}
          placeholder="license (например: CC-BY-4.0)"
          onChange={(e) => setImportLicense(e.target.value)}
        />
        <button
          className="retry-button"
          type="button"
          disabled={busy !== '' || !importFile}
          onClick={onImport}
        >
          Импортировать (как draft)
        </button>
      </div>

      {/* --- Поиск-превью --- */}
      <div className="panel">
        <h2>Поиск-превью (published)</h2>
        <div className="rag-toolbar">
          <input
            className="field"
            value={query}
            placeholder="поисковый запрос, ≥ 2 символов"
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            className="retry-button"
            type="button"
            disabled={busy !== '' || query.trim().length < 2}
            onClick={onSearch}
          >
            Найти топ-5
          </button>
        </div>
        {search && (
          <ul className="facts-list">
            {search.hits.map((hit) => (
              <li key={hit.chunkId}>
                [{hit.similarity.toFixed(3)}] {hit.titleRu} — {hit.text.slice(0, 160)}
              </li>
            ))}
            {search.hits.length === 0 && <li className="link-hint">Ничего не найдено</li>}
          </ul>
        )}
      </div>
    </section>
  );
}
