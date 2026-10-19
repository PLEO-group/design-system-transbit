const iconModules = import.meta.glob('../../dist/assets/react/icons/**/*.tsx', { eager: true });
const illustrationModules = import.meta.glob('../../dist/assets/react/illustrations/**/*.tsx', { eager: true });

const loadAssets = (modules, rootPath, type) => {
  return Object.entries(modules)
    .map(([path, componentModule]) => {
      const relativePath = path.substring(rootPath.length).replace(/\\/g, '/');
      const fileName = relativePath.substring(relativePath.lastIndexOf('/') + 1);
      const categoryPath = relativePath.substring(0, relativePath.lastIndexOf('/'));

      return {
        name: fileName.replace('.tsx', ''),
        category: categoryPath || 'Root',
        type,
        Component: componentModule.default,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
};

export const getIconList = () => loadAssets(iconModules, '../../dist/assets/react/icons/', 'icon');
export const getIllustrationList = () =>
  loadAssets(illustrationModules, '../../dist/assets/react/illustrations/', 'illustration');
