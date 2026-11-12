# Changelog

## Unreleased

### Added

- Opt-in responsive size and line height for `.ds-text.ds-text--<role>`,
  with generated unitless tokens, capped viewport scaling for Mobile (402px),
  Tablet (768px) and Desktop (1728px), and static fallbacks. Existing explicit
  typography scales and standalone variant classes remain supported.

- Export ready-to-use typography classes at
  `@pleodigital/design-system-transbit/css/typography.css`, generated from
  existing complete token roles in the `components` cascade layer. Classes
  follow the selected typography scale and allow utility overrides.
