import React from 'react';
import { AssetCard } from '../components/AssetCard';
import { getIconList, getIllustrationList } from '../utils/assetLoader';

export default {
  title: 'Assets/Icons and Illustrations',
  component: AssetCard,
};

const groupAssetsByCategory = (assets) => {
  return assets.reduce((acc, asset) => {
    acc[asset.category] = acc[asset.category] || [];
    acc[asset.category].push(asset);
    return acc;
  }, {});
};

const AssetGallery = ({ assets }) => {
  const groupedAssets = groupAssetsByCategory(assets);
  const categories = Object.keys(groupedAssets).sort();

  if (categories.length === 0) {
    return (
      <div style={{ padding: 24, color: '#667085' }}>
        No SVG assets found in the generated dist output.
      </div>
    );
  }

  return (
    <main style={{ padding: 24 }}>
      {categories.map((category) => (
        <section key={category} style={{ marginBottom: 40 }}>
          <h2 style={{ margin: '0 0 16px', fontSize: 20, lineHeight: '28px' }}>{category}</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {groupedAssets[category].map((asset) => (
              <AssetCard key={asset.name} asset={asset} />
            ))}
          </div>
        </section>
      ))}
    </main>
  );
};

export const IconsGallery = {
  render: () => <AssetGallery assets={getIconList()} />,
  name: 'Icons',
};

export const IllustrationsGallery = {
  render: () => <AssetGallery assets={getIllustrationList()} />,
  name: 'Illustrations',
};
