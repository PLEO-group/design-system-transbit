import { addons } from '@storybook/manager-api';
import { create } from '@storybook/theming/create';

addons.setConfig({
  theme: create({
    base: 'light',
    brandTitle: 'Flience Design System',
    brandImage: './icon_transbit_logo.svg',
    brandUrl: './',
    brandTarget: '_self',
  }),
});
