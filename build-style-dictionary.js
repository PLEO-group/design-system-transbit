const fs = require('fs');
const path = require('path');
const StyleDictionary = require('style-dictionary');

const ROOT = __dirname;
const TOKENS_DIR = path.join(ROOT, 'tokens');
const TEMP_DIR = path.join(ROOT, '.style-dictionary-tmp');
const OUTPUT_DIR = path.join(ROOT, 'dist', 'css');

function walkJsonFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return walkJsonFiles(fullPath);
    return entry.isFile() && entry.name.endsWith('.json') && !entry.name.startsWith('$') ? [fullPath] : [];
  });
}

function normalise(node) {
  if (Array.isArray(node)) return node.map(normalise);
  if (!node || typeof node !== 'object') return node;

  if (Object.prototype.hasOwnProperty.call(node, '$value') || Object.prototype.hasOwnProperty.call(node, 'value')) {
    const value = Object.prototype.hasOwnProperty.call(node, '$value') ? node.$value : node.value;
    return {
      // Keep aliases opaque to Style Dictionary. Several Tokens Studio sets
      // deliberately reuse a token path (for example light/dark values),
      // which would otherwise look like a circular reference during merging.
      value: typeof value === 'string' && /^\{[^}]+\}$/.test(value)
        ? `__transbit_reference__${value.slice(1, -1)}__`
        : value,
      type: node.$type || node.type || 'token',
      reference: typeof value === 'string' && /^\{[^}]+\}$/.test(value) ? value.slice(1, -1) : undefined,
    };
  }

  return Object.fromEntries(
    Object.entries(node)
      .filter(([key]) => !key.startsWith('$'))
      .map(([key, value]) => [key, normalise(value)])
  );
}

function kebab(value) {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ł/g, 'l')
    .replace(/Ł/g, 'L')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
}

function variableName(parts) {
  return `--${parts.map(kebab).filter(Boolean).join('-')}`;
}

function formatValue(token) {
  const reference = token.original && token.original.reference;
  if (typeof reference === 'string') {
    return `var(${variableName(reference.split('.'))})`;
  }

  const value = token.value;
  if (typeof value === 'number' || (typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value))) {
    const isFontWeight = token.path[0] === 'font-weight';
    return token.type === 'number' && !isFontWeight ? `${value}px` : String(value);
  }
  if (typeof value === 'string' && token.path.at(-1).toLowerCase() === 'family' && value.includes(' ')) {
    return `"${value.replace(/"/g, '\\"')}"`;
  }
  return String(value);
}

function selectorFor(relativeSource) {
  const parts = relativeSource.replace(/\\/g, '/').replace(/\.json$/, '').split('/');
  const [area, group, variant] = parts;
  const variantName = kebab(variant || group);

  if (area === 'DS' && group === 'Kolor') {
    const colorMode = variantName === 'jasny' ? 'light' : variantName === 'ciemny' ? 'dark' : variantName;
    return colorMode === 'light'
      ? ':root, :root[data-color-mode="light"]'
      : `:root[data-color-mode="${colorMode}"]`;
  }
  if (area === 'DS' && group === 'Typografia') {
    return variantName === 'desktop'
      ? ':root, :root[data-typography-scale="desktop"]'
      : `:root[data-typography-scale="${variantName}"]`;
  }
  if (area === 'Transbit' && group === 'Mobile') {
    return variantName === 'light'
      ? ':root, :root[data-transbit-mobile-theme="light"]'
      : `:root[data-transbit-mobile-theme="${variantName}"]`;
  }
  return ':root';
}

function sourceKey(relativeSource) {
  return relativeSource.replace(/\\/g, '/').replace(/\.json$/, '').split('/').map(kebab).join('.');
}

function build() {
  const sources = walkJsonFiles(TOKENS_DIR).sort();
  fs.rmSync(TEMP_DIR, { recursive: true, force: true });
  fs.rmSync(OUTPUT_DIR, { recursive: true, force: true });
  fs.mkdirSync(TEMP_DIR, { recursive: true });
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const entries = sources.map((absoluteSource) => {
    const relativeSource = path.relative(TOKENS_DIR, absoluteSource);
    const temporaryName = `${sourceKey(relativeSource)}.json`;
    const temporaryPath = path.join(TEMP_DIR, temporaryName);
    fs.writeFileSync(temporaryPath, `${JSON.stringify(normalise(JSON.parse(fs.readFileSync(absoluteSource, 'utf8'))), null, 2)}\n`);
    return { relativeSource, temporaryPath };
  });

  const typographyRoles = new Set();
  const typographyProperties = {
    'font-family': 'family',
    'font-size': 'size',
    'font-weight': 'weight',
    'line-height': 'line-height',
    'letter-spacing': 'letter-spacing',
  };

  StyleDictionary.registerFormat({
    name: 'transbit/css-variables',
    formatter: ({ dictionary, options }) => {
      const names = new Set(dictionary.allProperties.map((token) => variableName(token.path)));
      dictionary.allProperties
        .filter((token) => token.path[0] === 'typo' && token.path.length === 3)
        .forEach((token) => {
          const role = kebab(token.path[1]);
          if (Object.values(typographyProperties).every((property) => names.has(`--typo-${role}-${property}`))) {
            typographyRoles.add(role);
          }
        });
      const declarations = dictionary.allProperties
        // An alias from a themed token to the same CSS variable would become
        // self-referential. Omitting it correctly inherits the base token.
        .filter((token) => {
          const reference = token.original && token.original.reference;
          return !reference || variableName(token.path) !== variableName(reference.split('.'));
        })
        .flatMap((token) => {
          const name = variableName(token.path);
          const declarations = [`  ${name}: ${formatValue(token)};`];
          if (['font-size', 'line-height', 'letter-spacing'].includes(token.path[0]) ||
              (token.path[0] === 'typo' && ['size', 'line-height', 'letter-spacing'].includes(token.path.at(-1)))) {
            const reference = token.original && token.original.reference;
            declarations.push(`  ${name}-n: ${reference ? `var(${variableName(reference.split('.'))}-n)` : token.value};`);
          }
          return declarations;
        });
      return `/* Generated from tokens/${options.relativeSource}. Do not edit directly. */\n${options.selector} {\n${declarations.join('\n')}\n}\n`;
    },
  });

  entries.forEach(({ relativeSource, temporaryPath }) => {
    StyleDictionary.extend({
      source: [temporaryPath],
      platforms: {
        css: {
          transformGroup: 'css',
          buildPath: `${OUTPUT_DIR}${path.sep}`,
          files: [{
            destination: `${sourceKey(relativeSource)}.css`,
            format: 'transbit/css-variables',
            options: {
              relativeSource: relativeSource.replace(/\\/g, '/'),
              selector: selectorFor(relativeSource),
            },
          }],
        },
      },
    }).buildAllPlatforms();
  });
  const files = entries.map(({ relativeSource }) => `${sourceKey(relativeSource)}.css`);
  const bundle = files.map((file) => fs.readFileSync(path.join(OUTPUT_DIR, file), 'utf8').trim()).join('\n\n');
  fs.writeFileSync(path.join(OUTPUT_DIR, 'tokens.css'), `${bundle}\n`);
  const typography = [...typographyRoles].sort().map((role) => {
    const declarations = Object.entries(typographyProperties)
      .map(([property, token]) => `    ${property}: var(--typo-${role}-${token});`);
    return `  .ds-text--${role} {\n${declarations.join('\n')}\n  }`;
  });
  const scales = [
    { name: 'mobile', base: 402 },
    { name: 'tablet', base: 768, breakpoint: '(width >= 36rem) and (orientation: portrait) and (pointer: coarse), (width >= 36rem) and (orientation: portrait) and (pointer: fine)' },
    { name: 'laptop', base: 1280, breakpoint: '(width >= 80rem) and (width < 120rem) and (pointer: fine) and (orientation: landscape)' },
    { name: 'desktop', base: 1728, breakpoint: '(width >= 120rem) and (pointer: fine) and (orientation: landscape)' },
  ];
  const responsiveTokens = scales.map(({ name, base, breakpoint }) => {
    const source = fs.readFileSync(path.join(OUTPUT_DIR, `ds.typografia.${name}.css`), 'utf8');
    const declarations = source.slice(source.indexOf('{') + 1, source.lastIndexOf('}')).trim();
    // Automatic scales apply only to elements opting into responsive typography.
    const rule = `:root:not([data-typography-scale]) {\n  --ds-text-auto-rvw: calc(100vw / ${base});\n${declarations}\n}`;
    return breakpoint ? `@media ${breakpoint} {\n${rule}\n}` : rule;
  });
  const responsive = [...typographyRoles].sort().map((role) =>
    `  .ds-text.ds-text--${role} {\n` +
    `    --ds-text-size-n: var(--typo-${role}-size-n);\n` +
    `    --ds-text-line-height-n: var(--typo-${role}-line-height-n);\n` +
    `    font-size: calc(var(--ds-text-size-n) * var(--ds-text-rvw));\n` +
    `    line-height: calc(var(--ds-text-line-height-n) * var(--ds-text-rvw));\n` +
    `    letter-spacing: calc(var(--typo-${role}-letter-spacing-n) * var(--ds-text-rvw));\n  }`);
  // Keep automatic token values off :root so existing static classes stay unchanged.
  const automatic = responsiveTokens.join('\n').replaceAll(':root:not([data-typography-scale])', ':root:not([data-typography-scale]) .ds-text');
  const explicit = scales.map(({ name, base }) =>
    `:root[data-typography-scale="${name}"] {\n  --ds-text-auto-rvw: calc(100vw / ${base});\n}`).join('\n');
  fs.writeFileSync(path.join(OUTPUT_DIR, 'typography.css'),
    `/* Generated from typography tokens. Do not edit directly. */\n` +
    `@layer components {\n${automatic}\n${explicit}\n` +
    `  .ds-text {\n    --ds-text-rpx: var(--rpx, 1px);\n    --ds-text-rvw: var(--rvw, var(--ds-text-auto-rvw, var(--ds-text-rpx)));\n    margin: 0;\n  }\n` +
    `${typography.join('\n\n')}\n` +
    `@supports (font-size: min(1px, 2px)) {\n${responsive.join('\n\n')}\n}\n}\n`);
  fs.writeFileSync(path.join(OUTPUT_DIR, 'manifest.json'), `${JSON.stringify({ files }, null, 2)}\n`);
  fs.rmSync(TEMP_DIR, { recursive: true, force: true });
  console.log(`Built ${files.length} token set(s) in dist/css.`);
}

build();
