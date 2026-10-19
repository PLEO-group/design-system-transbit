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
    return token.type === 'number' ? `${value}px` : String(value);
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

  StyleDictionary.registerFormat({
    name: 'transbit/css-variables',
    formatter: ({ dictionary, options }) => {
      const declarations = dictionary.allProperties
        // An alias from a themed token to the same CSS variable would become
        // self-referential. Omitting it correctly inherits the base token.
        .filter((token) => {
          const reference = token.original && token.original.reference;
          return !reference || variableName(token.path) !== variableName(reference.split('.'));
        })
        .map((token) => `  ${variableName(token.path)}: ${formatValue(token)};`);
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
  fs.writeFileSync(path.join(OUTPUT_DIR, 'manifest.json'), `${JSON.stringify({ files }, null, 2)}\n`);
  fs.rmSync(TEMP_DIR, { recursive: true, force: true });
  console.log(`Built ${files.length} token set(s) in dist/css.`);
}

build();
