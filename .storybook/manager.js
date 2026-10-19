import { addons } from '@storybook/manager-api';
import { create } from '@storybook/theming/create';

addons.setConfig({
  theme: create({
    base: 'light',
    brandTitle: 'Flience Design System',
    brandImage: './logo_flience.svg',
    brandUrl: './',
    brandTarget: '_self',
  }),
});
