import React from 'react';
import './preview-styles.css';

const preview = {
  decorators: [
    (Story) => (
      <div className="storybook-shell">
        <Story />
      </div>
    ),
  ],
};

export default preview;
