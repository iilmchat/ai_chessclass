import type { ReactNode } from 'react';

interface StubPageProps {
  title: string;
  subtitle: string;
  notes: ReactNode;
}

/** Единая заглушка страницы домена: контент подключается по спринтам (TODO V0.1). */
export function StubPage({ title, subtitle, notes }: StubPageProps) {
  return (
    <section>
      <h1 className="page-title">{title}</h1>
      <p className="page-subtitle">{subtitle}</p>
      <div className="panel">
        <h2>Статус</h2>
        <p>Каркас страницы добавлен в S-01; функциональность — по спринтам этапа v0.1.</p>
        {notes}
      </div>
    </section>
  );
}
