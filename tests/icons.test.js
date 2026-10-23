const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { test } = require('node:test');

test('every source icon has an exported, resizable currentColor component and unchanged raw copy', () => {
  const index = fs.readFileSync('dist/assets/react/icons/index.ts', 'utf8');
  for (const file of fs.readdirSync('assets/icons').filter((name) => name.endsWith('.svg'))) {
    const name = path.basename(file, '.svg').split('_')
      .map((part) => part[0].toUpperCase() + part.slice(1)).join('');
    const component = fs.readFileSync(`dist/assets/react/icons/${name}.tsx`, 'utf8');
    assert.ok(index.includes(`export { default as ${name} } from "./${name}";`));
    assert.match(component, /viewBox="[^"]+"/);
    assert.match(component, /fill="currentColor"/);
    assert.match(component, /\{\.\.\.props\}/);
    assert.doesNotMatch(component, /\b(?:width|height)="/);
    assert.doesNotMatch(component, /#[\da-f]{3,8}\b/i);
    assert.equal(fs.readFileSync(`dist/assets/angular/svg-raw/icons/${file}`, 'utf8'),
      fs.readFileSync(`assets/icons/${file}`, 'utf8'));
  }
});

test('npm package includes icons and supports public imports', () => {
  const packageName = require('../package.json').name;
  assert.equal(require.resolve(`${packageName}/icons`),
    path.resolve('dist/assets/react/icons/index.ts'));
  assert.equal(require.resolve(`${packageName}/dist/assets/react/icons/IconUiSearch.tsx`),
    path.resolve('dist/assets/react/icons/IconUiSearch.tsx'));
  const [pack] = JSON.parse(execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], {
    encoding: 'utf8',
  }));
  const files = new Set(pack.files.map((file) => file.path));
  for (const directory of ['dist/assets/react/icons', 'dist/assets/angular/svg-raw/icons']) {
    for (const file of fs.readdirSync(directory)) {
      assert.ok(files.has(`${directory}/${file}`), `${directory}/${file} missing from package`);
    }
  }
});
