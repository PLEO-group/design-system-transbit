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

test('automatic dimensions are continuous and match DS values at design widths', () => {
  const { runInNewContext } = require('node:vm');
  const css = fs.readFileSync('dist/css/typography.css', 'utf8');
  const tokens = fs.readFileSync('dist/css/tokens.css', 'utf8');
  const numbers = Object.fromEntries([...tokens.matchAll(/(--(?:font-size|line-height)-[\w-]+-n): (\d+(?:\.\d+)?);/g)]
    .map(([, name, value]) => [name, Number(value)]));
  const scales = ['mobile', 'tablet', 'desktop'].map((scale) =>
    fs.readFileSync(`dist/css/ds.typografia.${scale}.css`, 'utf8'));
  const rules = [...css.matchAll(/:where\(:root:not\(\[data-typography-scale\]\)\) \.ds-text\.ds-text--([\w-]+) \{([^}]+)\}/g)];
  const roles = [...css.matchAll(/^  \.ds-text--([\w-]+) \{/gm)].map(([, role]) => role);
  assert.deepEqual(rules.map(([, role]) => role), roles);
  for (const [, role, body] of rules) {
    assert.doesNotMatch(body, /var\(--rvw/);
    for (const [property, dimension] of [['font-size', 'size'], ['line-height', 'line-height']]) {
      const expression = body.match(new RegExp(`${property}: calc\\(([\\s\\S]*?)\\);`))[1];
      const measure = (width) => {
        const arithmetic = expression
          .replace(/var\((--[\w-]+)\)/g, (_, name) => {
            assert.ok(name === '--ds-text-rpx' || Object.hasOwn(numbers, name), name);
            return name === '--ds-text-rpx' ? '1' : String(numbers[name]);
          })
          .replace(/calc\(/g, '(').replace(/100vw/g, String(width)).replace(/px/g, '');
        return runInNewContext(arithmetic, {
          min: Math.min,
          clamp: (lower, value, upper) => Math.max(lower, Math.min(value, upper)),
        });
      };
      for (const [index, width] of [402, 768, 1728].entries()) {
        const alias = scales[index].match(new RegExp(`--typo-${role}-${dimension}-n: var\\(([^)]+)\\)`));
        assert.ok(alias, `${role} ${dimension}`);
        assert.equal(measure(width), numbers[alias[1]], `${role} ${property} at ${width}`);
      }
      assert.equal(measure(201), measure(402) / 2);
      assert.equal(measure(2560), measure(1728));
      for (const width of [402, 576, 768, 1024, 1280, 1728, 1920]) {
        assert.ok(Math.abs(measure(width + 1) - measure(width - 1)) < 0.6,
          `${role} ${property} jumps at ${width}`);
      }
    }
  }
});
