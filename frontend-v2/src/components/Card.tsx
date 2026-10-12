import type { HTMLAttributes, ReactNode } from 'react';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  raised?: boolean;
  children: ReactNode;
}

/** Карточка поверхности. Только токены, без постоянных свечений. */
export function Card({ raised = false, children, className, ...rest }: CardProps) {
  const classes = ['card', raised ? 'card--raised' : '', className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  title: string;
  kicker?: string;
  action?: ReactNode;
}

export function CardHeader({ title, kicker, action }: CardHeaderProps) {
  return (
    <div className="card__header">
      <div className="card__headings">
        {kicker ? <span className="kicker">{kicker}</span> : null}
        <h3 className="card__title">{title}</h3>
      </div>
      {action}
    </div>
  );
}

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: 'neutral' | 'accent' | 'success' | 'error' | 'info';
  children: ReactNode;
}

/** Метка. Цвет несёт смысл всегда вместе с текстом, не вместо него. */
export function Chip({ tone = 'neutral', children, className, ...rest }: ChipProps) {
  const classes = ['chip', `chip--${tone}`, className ?? ''].filter(Boolean).join(' ');
  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  );
}
