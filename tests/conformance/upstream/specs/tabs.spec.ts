/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { test, expect } from '../fixtures/fixtures.js';

import type { Client } from '@modelcontextprotocol/sdk/client/index.js';

async function createTab(client: Client, title: string, body: string) {
  await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'new',
    },
  });
  return await client.callTool({
    name: 'browser_navigate',
    arguments: {
      url: `data:text/html,<title>${title}</title><body>${body}</body>`,
    },
  });
}

test('list initial tabs', async ({ client }) => {
  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'list',
    },
  })).toHaveResponse({
    result: `- 0: (current) [](about:blank)`,
  });
});

test('list first tab', async ({ client }) => {
  await createTab(client, 'Tab one', 'Body one');
  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'list',
    },
  })).toHaveResponse({
    result: `- 0: [](about:blank)
- 1: (current) [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)`,
  });
});

test('create new tab', async ({ client }) => {
  expect(await createTab(client, 'Tab one', 'Body one')).toHaveResponse({
    tabs: `- 0: [](about:blank)
- 1: (current) [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)`,
    snapshot: `- generic [active] [ref=e1]: Body one`,
  });

  expect(await createTab(client, 'Tab two', 'Body two')).toHaveResponse({
    tabs: `- 0: [](about:blank)
- 1: [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)
- 2: (current) [Tab two](data:text/html,<title>Tab two</title><body>Body two</body>)`,
    snapshot: `- generic [active] [ref=e1]: Body two`,
  });
  expect(await client.callTool({
    name: 'browser_snapshot',
    arguments: {},
  })).toHaveResponse({
    page: expect.stringContaining('Page URL: data:text/html,<title>Tab two</title><body>Body two</body>'),
  });
});

test('create new tab with url', async ({ client }) => {
  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'new',
      url: `data:text/html,<title>Tab one</title><body>Body one</body>`,
    },
  })).toHaveResponse({
    result: `- 0: [](about:blank)
- 1: (current) [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)`,
  });
});

test('select tab', async ({ client }) => {
  await createTab(client, 'Tab one', 'Body one');
  await createTab(client, 'Tab two', 'Body two');

  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'select',
      index: 1,
    },
  })).toHaveResponse({
    result: `- 0: [](about:blank)
- 1: (current) [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)
- 2: [Tab two](data:text/html,<title>Tab two</title><body>Body two</body>)`,
  });

  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'select',
      index: 0,
    },
  })).toHaveResponse({
    result: `- 0: (current) [](about:blank)
- 1: [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)
- 2: [Tab two](data:text/html,<title>Tab two</title><body>Body two</body>)`,
  });
});

test('close tab', async ({ client }) => {
  await createTab(client, 'Tab one', 'Body one');
  await createTab(client, 'Tab two', 'Body two');

  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'close',
      index: 2,
    },
  })).toHaveResponse({
    result: `- 0: [](about:blank)
- 1: (current) [Tab one](data:text/html,<title>Tab one</title><body>Body one</body>)`,
  });
});

test('tracks browser context pages opened outside browser_tabs', async ({ client }) => {
  await client.callTool({
    name: 'browser_navigate',
    arguments: {
      url: `data:text/html,<title>Main</title><body>Main body</body>`,
    },
  });

  await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code: `popup = await page.context.new_page()
await popup.goto("data:text/html,<title>Popup</title><body>Popup body</body>")`,
    },
  });

  await expect.poll(async () => {
    const result = await client.callTool({
      name: 'browser_tabs',
      arguments: {
        action: 'list',
      },
    });
    return result.content[0].type === 'text' ? result.content[0].text : '';
  }).toContain('[Popup](data:text/html,<title>Popup</title><body>Popup body</body>)');

  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'select',
      index: 1,
    },
  })).toHaveResponse({
    result: expect.stringContaining('- 1: (current) [Popup](data:text/html,<title>Popup</title><body>Popup body</body>)'),
  });

  expect(await client.callTool({
    name: 'browser_tabs',
    arguments: {
      action: 'close',
      index: 1,
    },
  })).toHaveResponse({
    result: expect.not.stringContaining('[Popup]'),
  });
});

test.skip('reuse first tab when navigating', async () => {
  // Requires CDP CLI parity; tracked in Slice 15.
});
