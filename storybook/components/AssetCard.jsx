import React from 'react';

const cardStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'space-between',
  minWidth: 160,
  minHeight: 120,
  padding: 16,
  border: '1px solid #e4e6ec',
  borderRadius: 8,
  color: '#1d2b4a',
  boxShadow: '0 1px 3px rgba(16, 24, 40, 0.08)',
};

export const AssetCard = ({ asset }) => {
  const size = asset.type === 'icon' ? 28 : 160;

  return (
    <div style={cardStyle} className={asset.type === 'icon' ? 'asset-card' : ''}>
      <div style={{ width: size, height: asset.type === 'icon' ? size : 'auto' }}>
        {asset.Component && <asset.Component aria-hidden="true" style={{ maxWidth: '100%', height: 'auto' }} />}
      </div>
      <p style={{ margin: '12px 0 0', fontSize: 13, wordBreak: 'break-word' }}>{asset.name}</p>
    </div>
  );
};
