/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import { test, expect } from '../fixtures/fixtures.js';

test.use({ mcpCaps: ['devtools'] });

test('browser_highlight', async ({ client, server }) => {
  server.setContent('/', `<button>Submit</button>`, 'text/html');
  await client.callTool({ name: 'browser_navigate', arguments: { url: server.PREFIX } });
  await client.callTool({ name: 'browser_snapshot' });

  expect(await client.callTool({
    name: 'browser_highlight',
    arguments: { element: 'Submit button', target: 'e2' },
  })).toHaveResponse({
    result: `Highlighted Submit button`,
  });
});

test('browser_highlight with style', async ({ client, server }) => {
  server.setContent('/', `<button>Submit</button>`, 'text/html');
  await client.callTool({ name: 'browser_navigate', arguments: { url: server.PREFIX } });
  await client.callTool({ name: 'browser_snapshot' });

  expect(await client.callTool({
    name: 'browser_highlight',
    arguments: {
      element: 'Submit button',
      target: 'e2',
      style: 'outline: 3px solid rgb(255, 0, 0); background-color: rgba(0, 255, 0, 0.25)',
    },
  })).toHaveResponse({
    result: `Highlighted Submit button`,
  });

});

test('browser_hide_highlight', async ({ client, server }) => {
  server.setContent('/', `<button>Submit</button>`, 'text/html');
  await client.callTool({ name: 'browser_navigate', arguments: { url: server.PREFIX } });
  await client.callTool({ name: 'browser_snapshot' });
  await client.callTool({ name: 'browser_highlight', arguments: { element: 'Submit button', target: 'e2' } });

  expect(await client.callTool({
    name: 'browser_hide_highlight',
    arguments: { element: 'Submit button', target: 'e2' },
  })).toHaveResponse({
    result: `Hid highlight for Submit button`,
  });
});

test.skip('browser_resume completes when context closes', async () => {
  // Requires the upstream bound-browser fixture so the test can pause and close
  // the same browser context controlled by the MCP server.
});

test('browser_hide_highlight all', async ({ client, server }) => {
  server.setContent('/', `<button>Submit</button><a href="#">Go</a>`, 'text/html');
  await client.callTool({ name: 'browser_navigate', arguments: { url: server.PREFIX } });
  await client.callTool({ name: 'browser_snapshot' });
  await client.callTool({ name: 'browser_highlight', arguments: { element: 'Submit button', target: 'e2' } });
  await client.callTool({ name: 'browser_highlight', arguments: { element: 'Go link', target: 'e3' } });

  expect(await client.callTool({
    name: 'browser_hide_highlight',
    arguments: {},
  })).toHaveResponse({
    result: 'Hid page highlight',
  });
});
