import React from 'react';

const cardStyle = {
  width: 172,
  flexShrink: 0,
};

const swatchStyle = {
  width: '100%',
  height: 108,
  borderRadius: 8,
  border: '1px solid rgba(16, 24, 40, 0.12)',
  boxShadow: '0 1px 3px rgba(16, 24, 40, 0.12)',
};

const labelStyle = {
  margin: '10px 0 0',
  color: '#3c3c3b',
  fontSize: 14,
  lineHeight: '18px',
  wordBreak: 'break-word',
};

const valueStyle = {
  margin: '2px 0 0',
  color: '#575756',
  fontSize: 13,
  lineHeight: '18px',
  wordBreak: 'break-word',
};

const metaStyle = {
  margin: '6px 0 0',
  color: '#1d2b4a',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  fontSize: 12,
  lineHeight: '16px',
  wordBreak: 'break-word',
};

export const TokenSwatch = ({ token, color, meta }) => {
  return (
    <div style={cardStyle} title={`${token.name}: ${token.value}`}>
      <div
        style={{
          ...swatchStyle,
          background: color || token.cssValue || token.value,
        }}
      />
      <p style={labelStyle}>{token.name}</p>
      <p style={valueStyle}>{String(token.value)}</p>
      {meta ? <p style={metaStyle}>{meta}</p> : null}
    </div>
  );
};
