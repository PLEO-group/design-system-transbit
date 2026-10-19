import React from 'react';
import { TokenSwatch } from '../TokenSwatch';

const sectionStyle = {
  padding: '24px 0',
  borderBottom: '1px solid rgba(16, 24, 40, 0.12)',
};

const gridStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '24px 12px',
};

const titleStyle = {
  margin: '0 0 16px',
  color: 'var(--color-text-primary)',
  fontSize: 20,
  lineHeight: '28px',
};

const previewStyle = {
  width: '100%',
  minHeight: 88,
  padding: 16,
  border: '1px solid var(--color-border-subtle)',
  borderRadius: 8,
  background: 'var(--color-bg-elevated)',
  color: 'var(--color-text-primary)',
};

function tailwindClassName(token, mode) {
  const path = token.path.join('-');

  if (mode === 'text') {
    return `text-${path}`;
  }

  if (mode === 'border') {
    return `border-${path}`;
  }

  return `bg-${path}`;
}

const ThemePreview = ({ token, mode }) => {
  const color = `var(${token.name})`;
  const className = tailwindClassName(token, mode);

  if (mode === 'text') {
    return (
      <div style={previewStyle}>
        <p style={{ margin: 0, color, fontSize: 20, lineHeight: '28px' }}>Flience design tokens preview</p>
        <p
          style={{
            margin: '12px 0 0',
            color: 'var(--color-text-secondary)',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 12,
            lineHeight: '16px',
          }}
        >
          {className}
        </p>
      </div>
    );
  }

  if (mode === 'border') {
    return (
      <div style={{ ...previewStyle, border: `4px solid ${color}` }}>
        <p
          style={{
            margin: 0,
            color: 'var(--color-text-secondary)',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 12,
            lineHeight: '16px',
          }}
        >
          {className}
        </p>
      </div>
    );
  }

  return <TokenSwatch token={token} color={color} meta={className} />;
};

export const Section = ({ title, tokens, mode = 'background' }) => {
  return (
    <section style={sectionStyle}>
      <h2 style={titleStyle}>{title}</h2>
      <div style={gridStyle}>
        {tokens.map((token) => (
          <ThemePreview key={token.name} token={token} mode={mode} />
        ))}
      </div>
    </section>
  );
};
