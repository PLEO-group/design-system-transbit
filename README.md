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

Run `npm test` to check role coverage, variable references, exports and
repeatable token output.
