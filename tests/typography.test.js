const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { test } = require('node:test');

const properties = {
  'font-family': 'family',
  'font-size': 'size',
  'font-weight': 'weight',
  'line-height': 'line-height',
  'letter-spacing': 'letter-spacing',
};

test('every complete typography role uses exactly five existing variables', () => {
  const roles = new Set();
  for (const file of fs.readdirSync('tokens/DS/Typografia')) {
    const tokens = JSON.parse(fs.readFileSync(`tokens/DS/Typografia/${file}`, 'utf8')).typo;
    for (const [role, tokensByProperty] of Object.entries(tokens)) {
      if (Object.values(properties).every((property) => tokensByProperty[property]?.$value !== undefined)) {
        roles.add(role);
      }
    }
  }
  const css = fs.readFileSync('dist/css/typography.css', 'utf8');
  assert.match(css, /@layer components \{/);
  const rules = [...css.matchAll(/^  \.ds-text--([\w-]+) \{([^}]+)\}/gm)];
  assert.deepEqual(rules.map(([, role]) => role), [...roles].sort());
  const variables = fs.readFileSync('dist/css/tokens.css', 'utf8');
  for (const [, role, body] of rules) {
    assert.equal(body.trim(), Object.entries(properties)
      .map(([property, token]) => `${property}: var(--typo-${role}-${token});`).join('\n    '));
    for (const token of Object.values(properties)) {
      assert.ok(variables.includes(`--typo-${role}-${token}:`));
    }
  }
});

test('token build is repeatable and preserves existing package entry points', () => {
  const before = fs.readdirSync('dist/css').map((file) => [file, fs.readFileSync(`dist/css/${file}`, 'utf8')]);
  execFileSync(process.execPath, ['build-style-dictionary.js']);
  const after = fs.readdirSync('dist/css').map((file) => [file, fs.readFileSync(`dist/css/${file}`, 'utf8')]);
  assert.deepEqual(after, before);
  const name = require('../package.json').name;
  assert.equal(require.resolve(name), require.resolve(`${name}/css/tokens.css`));
  assert.ok(require.resolve(`${name}/css/typography.css`).endsWith('/dist/css/typography.css'));
  assert.ok(require.resolve(`${name}/css/ds.typografia.desktop.css`).endsWith('/dist/css/ds.typografia.desktop.css'));
});


test('responsive sizes have unitless aliases, automatic scales and guarded fallbacks', () => {
  const css = fs.readFileSync('dist/css/typography.css', 'utf8');
  const tokens = fs.readFileSync('dist/css/tokens.css', 'utf8');
  assert.match(css, /@supports \(font-size: min\(1px, 2px\)\)/);
  assert.match(css, /@media \(width >= 36rem\)/);
  assert.match(css, /@media \(width >= 64rem\)/);
  for (const base of [402, 768, 1728]) assert.ok(css.includes(`calc(100vw / ${base})`));
  for (const [, name] of tokens.matchAll(/(--typo-[\w-]+-(?:size|line-height)):/g)) {
    assert.ok(tokens.includes(`${name}-n:`));
  }
  for (const [, role] of css.matchAll(/^  \.ds-text--([\w-]+) \{/gm)) {
    assert.ok(css.includes(`.ds-text.ds-text--${role}`));
    assert.ok(css.includes(`--ds-text-size-n: var(--typo-${role}-size-n)`));
    assert.ok(css.includes(`--ds-text-line-height-n: var(--typo-${role}-line-height-n)`));
  }
});
