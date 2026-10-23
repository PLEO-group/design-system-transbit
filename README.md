# design-system-transbit

Repository for Transbit design tokens exported from Tokens Studio.

## Build tokens

```sh
npm install
npm run build
```

The build normalizes the DTCG JSON files in `tokens/` and writes CSS to
`dist/css/`. `dist/css/tokens.css` contains every token set; individual files
are listed in `dist/css/manifest.json`.

Theme selectors in the combined stylesheet:

- `data-color-mode="light"` / `data-color-mode="dark"`
- `data-typography-scale="mobile" | "tablet" | "laptop" | "desktop"`
- `data-transbit-mobile-theme="light"` / `data-transbit-mobile-theme="dark"`

## Storybook

```sh
npm run storybook
```

The initial `Tokens/Overview` story previews representative colour and
typography tokens. Use the toolbar to switch token modes. Generate the static
site with `npm run build-storybook`.

The development server runs at `http://localhost:6007`, leaving port 6006
available for the Transbit Storybook.

## Typography classes

Import the token values before the ready-to-use typography classes:

```js
import "@pleodigital/design-system-transbit/css/tokens.css";
import "@pleodigital/design-system-transbit/css/typography.css";
```

```html
<html data-typography-scale="mobile">
  <body>
    <h1 class="ds-text--h1">Transbit</h1>
    <p class="ds-text--body font-semibold">Body text with a local weight override.</p>
  </body>
</html>
```

The build derives `.ds-text--<role>` classes from complete typography token
roles. Each class sets only font family, size, weight, line height and letter
spacing through existing CSS variables. Change `data-typography-scale` on
`<html>` to `mobile`, `tablet`, `laptop` or `desktop` without changing classes.
Font files must be loaded by the application.

Classes live in `@layer components`. With Tailwind CSS 4, load the Tailwind
stylesheet first so its `theme, base, components, utilities` layer order is
established before the package styles. Alternatively, declare that order at
the start of the application's CSS. Utilities such as `font-semibold` then
override the role weight with 600. No scanning of this package in
`node_modules` is needed: all role classes are already present in the CSS.

## React icons and raw SVG

`npm run transform:icons` generates TypeScript React components and `index.ts`
from `assets/icons/*.svg` in `dist/assets/react/icons/`. SVGO removes fixed
dimensions and converts icon colors to `currentColor`; set size and color through props.

```tsx
import { IconUiSearch } from '@pleodigital/design-system-transbit/icons';
// Alternatively:
// import IconUiSearch from '@pleodigital/design-system-transbit/dist/assets/react/icons/IconUiSearch.tsx';

<IconUiSearch width={24} height={24} style={{ color: 'green' }} />
```

The package ships source TSX. Configure your application's bundler to transpile
this dependency and provide React in the consuming application.

`npm run build` also copies the original SVG files unchanged to
`dist/assets/angular/svg-raw/icons/`. These are framework-independent SVG assets,
not Angular components; they retain their original colors and dimensions.
All `dist/` files are included in the npm package. CI builds before publishing;
`prepublishOnly` also rebuilds for manual `npm publish`.

Run `npm test` to check typography, generated icons, raw SVG copies and package exports.

## Responsive typography

Use the same CSS imports as above. Add the base class to opt into responsive
font size and line height:

```html
<html>
  <body>
    <h1 class="ds-text ds-text--display">Responsive heading</h1>
    <p class="ds-text ds-text--body font-semibold">Responsive body text</p>
  </body>
</html>
```

Without `data-typography-scale`, responsive elements select Mobile tokens below
`36rem`, Tablet tokens from `36rem`, and Desktop tokens from `64rem`. The design
widths are respectively 402px, 768px and 1728px. Each dimension is computed as
`min(token × viewport width / design width, token × 1px)` using generated
unitless `-n` tokens. Values come from the existing token sources, including
aliases; no separate role values are maintained.

Breakpoint changes can cause jumps, including a smaller size on entering the
Desktop scale. This is capped scaling within each range, not continuous
interpolation between design values. Existing classes without `.ds-text`
retain their static behavior. `.ds-text` also resets margin to zero.

Remove `data-typography-scale` from `<html>` for automatic breakpoint selection.
An explicit `mobile`, `tablet` or `desktop` attribute locks the selected token
set and design width regardless of viewport. The existing `laptop` mode keeps
its static dimensions because this responsive model defines no Laptop design
width.

Applications can override `--rpx` (default `1px`) and `--rvw` (responsive pixel).
If no responsive pixel is available, the base class uses the regular pixel.
Static size and line-height declarations remain outside the `@supports`
block; browsers without `min()` use these values. All typography rules stay
in `components`, so Tailwind utilities can override them.
