import type { ReactNode } from 'react';

export type SkeletonShape = 'card' | 'list' | 'wheel' | 'line';

export interface SkeletonProps {
  shape?: SkeletonShape;
  count?: number;
}

/** Скелетон соответствующей формы, а не универсальный прямоугольник. */
export function Skeleton({ shape = 'line', count = 1 }: SkeletonProps) {
  const items = Array.from({ length: Math.max(1, count) }, (_, index) => (
    <div key={index} className={`skeleton skeleton--${shape}`} aria-hidden="true" />
  ));
  return <>{items}</>;
}

export interface EmptyStateProps {
  title: string;
  hint?: string;
  action?: ReactNode;
}

/** Пустое состояние всегда с живым призывом к действию. */
export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="state state--empty" role="status">
      <p className="state__title">{title}</p>
      {hint ? <p className="state__hint">{hint}</p> : null}
      {action ? <div className="state__action">{action}</div> : null}
    </div>
  );
}

export interface ErrorStateProps {
  title: string;
  hint?: string | undefined;
  retryLabel?: string | undefined;
  onRetry?: (() => void) | undefined;
}

/** Ошибка: человеческий текст + повтор, без кодов и стектрейсов. */
export function ErrorState({ title, hint, retryLabel, onRetry }: ErrorStateProps) {
  return (
    <div className="state state--error" role="alert">
      <p className="state__title">
        <span aria-hidden="true">⚠ </span>
        {title}
      </p>
      {hint ? <p className="state__hint">{hint}</p> : null}
      {onRetry && retryLabel ? (
        <div className="state__action">
          <button type="button" className="btn btn--secondary btn--md" onClick={onRetry}>
            {retryLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}
