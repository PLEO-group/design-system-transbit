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
available for the Flience Storybook.
