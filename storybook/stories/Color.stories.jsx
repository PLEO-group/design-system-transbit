import React from 'react';
import sourceTokens from '../../tokens/DS/Kolor-bazowy/Value.json';
import { TokenSwatch } from '../components/TokenSwatch';
import { flattenTokens, groupByFirstSegment, sortTokens } from '../utils';

export default {
  title: 'Tokens/Colors',
  component: TokenSwatch,
  parameters: {
    layout: 'fullscreen',
  },
};

export const Palette = {
  name: 'Core color tokens',
  render: () => {
    const tokens = sortTokens(flattenTokens(sourceTokens).filter((token) => token.type === 'color'));
    const groupedTokens = groupByFirstSegment(tokens);

    return (
      <main style={{ minHeight: '100vh', background: '#ffffff', color: '#101828', padding: 24 }}>
        <h1 style={{ margin: '0 0 32px', color: '#1d2b4a', fontSize: 32, lineHeight: '40px' }}>Color tokens</h1>
        {Object.keys(groupedTokens)
          .sort()
          .map((groupName) => (
            <section key={groupName} style={{ marginBottom: 32, paddingBottom: 24, borderBottom: '1px solid #e4e7ec' }}>
              <h2 style={{ margin: '0 0 16px', color: '#3c3c3b', fontSize: 20, lineHeight: '28px' }}>{groupName}</h2>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px 12px' }}>
                {groupedTokens[groupName].map((token) => (
                  <TokenSwatch key={token.name} token={token} />
                ))}
              </div>
            </section>
          ))}
      </main>
    );
  },
};
