import type { ReactNode } from 'react';

export interface DemoBadgeProps {
  label: string;
  hint?: string | undefined;
}

/**
 * Явная пометка демонстрационных данных.
 * Требование приёмки A1-9: каждый placeholder-экран несёт видимую пометку,
 * чтобы демо-данные не выглядели как результат работы API.
 */
export function DemoBadge({ label, hint }: DemoBadgeProps) {
  return (
    <div className="demo-badge" role="note">
      <span className="demo-badge__label">{label}</span>
      {hint ? <span className="demo-badge__hint">{hint}</span> : null}
    </div>
  );
}

export interface ScreenProps {
  title: string;
  kicker?: string;
  action?: ReactNode;
  demo?: DemoBadgeProps;
  children: ReactNode;
}

/**
 * Общая обёртка экрана: заголовок, действие и пометка демо-данных.
 * Экран остаётся самостоятельным: свой заголовок, своя структура.
 */
export function Screen({ title, kicker, action, demo, children }: ScreenProps) {
  return (
    <section className="screen">
      <header className="screen__head">
        <div className="screen__headings">
          {kicker ? <span className="kicker">{kicker}</span> : null}
          <h1 className="screen__title">{title}</h1>
        </div>
        {action ? <div className="screen__action">{action}</div> : null}
      </header>
      {demo ? <DemoBadge label={demo.label} hint={demo.hint} /> : null}
      <div className="screen__body">{children}</div>
    </section>
  );
}

/** Блок с призывом к действию: используется в сводках Home. */
export function ActionTile({
  title,
  hint,
  onClick,
}: {
  title: string;
  hint?: string;
  onClick?: () => void;
}) {
  return (
    <button type="button" className="action-tile" onClick={onClick}>
      <span className="action-tile__title">{title}</span>
      {hint ? <span className="action-tile__hint">{hint}</span> : null}
    </button>
  );
}
