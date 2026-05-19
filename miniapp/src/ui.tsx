import { ReactNode, ButtonHTMLAttributes } from 'react';

export function List({ children }: { children: ReactNode }) {
  return <div style={{ padding: '0 0 24px' }}>{children}</div>;
}

export function Section({
  header, footer, children,
}: { header?: string; footer?: string; children: ReactNode }) {
  return (
    <div style={{ marginTop: 16 }}>
      {header && (
        <div style={{
          padding: '0 16px 6px',
          fontSize: 13,
          color: 'var(--tg-theme-hint-color, #8e8e93)',
          textTransform: 'uppercase',
          letterSpacing: 0.5,
        }}>
          {header}
        </div>
      )}
      <div style={{
        background: 'var(--tg-theme-secondary-bg-color, #f2f2f7)',
        borderRadius: 12,
        margin: '0 16px',
        overflow: 'hidden',
      }}>
        {children}
      </div>
      {footer && (
        <div style={{
          padding: '6px 16px 0',
          fontSize: 13,
          color: 'var(--tg-theme-hint-color, #8e8e93)',
        }}>
          {footer}
        </div>
      )}
    </div>
  );
}

export function Cell({
  description, onClick, children,
}: { description?: string; onClick?: () => void; children: ReactNode }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '0.5px solid var(--tg-theme-hint-color, #c6c6c8)',
        cursor: onClick ? 'pointer' : 'default',
        background: 'transparent',
      }}
    >
      <div>
        <div style={{ color: 'var(--tg-theme-text-color, #000)', fontSize: 16 }}>{children}</div>
        {description && (
          <div style={{ color: 'var(--tg-theme-hint-color, #8e8e93)', fontSize: 13, marginTop: 2 }}>
            {description}
          </div>
        )}
      </div>
      {onClick && <span style={{ color: 'var(--tg-theme-hint-color, #c6c6c8)', fontSize: 20 }}>›</span>}
    </div>
  );
}

export function Button({
  children, stretched, size, ...props
}: { children: ReactNode; stretched?: boolean; size?: 's' | 'm' | 'l' } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      style={{
        display: 'block',
        width: stretched ? '100%' : 'auto',
        padding: size === 'l' ? '14px 24px' : '10px 20px',
        background: 'var(--tg-theme-button-color, #007aff)',
        color: 'var(--tg-theme-button-text-color, #fff)',
        border: 'none',
        borderRadius: 12,
        fontSize: size === 'l' ? 17 : 15,
        fontWeight: 600,
        cursor: props.disabled ? 'not-allowed' : 'pointer',
        opacity: props.disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  );
}

export function Placeholder({
  header, description, children,
}: { header?: string; description?: string; children?: ReactNode }) {
  return (
    <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--tg-theme-text-color, #000)' }}>
      {header && <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>{header}</div>}
      {description && <div style={{ fontSize: 15, color: 'var(--tg-theme-hint-color, #8e8e93)' }}>{description}</div>}
      {children}
    </div>
  );
}

export function Spinner(_props?: { size?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
      <div style={{
        width: 28, height: 28,
        border: '3px solid var(--tg-theme-hint-color, #c6c6c8)',
        borderTopColor: 'var(--tg-theme-button-color, #007aff)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
    </div>
  );
}
