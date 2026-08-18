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

import fs from 'fs';

import { test, expect, parseResponse, consoleEntries } from '../fixtures/fixtures.js';

test('browser_run_code_unsafe', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Submit')">Submit</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const code = 'await page.get_by_role("button", name="Submit").click()';
  const response = parseResponse(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code,
    },
  }));
  const content = await consoleEntries(response);
  expect(content).toContain('[LOG] Submit');
});

test('browser_run_code_unsafe block', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Submit')">Submit</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const response = parseResponse(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code: 'await page.get_by_role("button", name="Submit").click()\nawait page.get_by_role("button", name="Submit").click()',
    },
  }));

  expect(response).toEqual(expect.objectContaining({
    code: expect.stringContaining(`await page.get_by_role("button", name="Submit").click()`),
  }));

  const content = await consoleEntries(response);
  expect(content).toMatch(/\[LOG\] Submit.*\n.*\[LOG\] Submit/);
});

test('browser_run_code_unsafe no-require', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Submit')">Submit</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  expect(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code: `require("fs")`,
    },
  })).toHaveResponse({
    error: expect.stringContaining(`name 'require' is not defined`),
    isError: true,
  });

  expect(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code: `import os`,
    },
  })).toHaveResponse({
    error: expect.stringContaining(`__import__ not found`),
    isError: true,
  });

  expect(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code: `open("/tmp/playwright-python-mcp-blocked", "w")`,
    },
  })).toHaveResponse({
    error: expect.stringContaining(`name 'open' is not defined`),
    isError: true,
  });
});

test('browser_run_code_unsafe return value', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Submit')">Submit</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const code = 'await page.get_by_role("button", name="Submit").click()\nreturn { "message": "Hello, world!" }';

  const response = parseResponse(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: {
      code,
    },
  }));
  expect(response).toEqual(expect.objectContaining({
    code,
    result: '{"message":"Hello, world!"}',
  }));

  const content = await consoleEntries(response);
  expect(content).toContain('[LOG] Submit');
});

test('browser_run_code_unsafe route handler exception keeps server alive', async ({ client, server }) => {
  server.setContent('/', '<button>Submit</button>', 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const code = `raise RuntimeError("route handler failed")`;
  expect(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: { code },
  })).toHaveResponse({
    error: expect.stringContaining('route handler failed'),
    isError: true,
  });

  // Subsequent tool calls should still work because the transport remains alive.
  const followUp = await client.callTool({
    name: 'browser_tabs',
    arguments: { action: 'list' },
  });
  expect(followUp.isError).toBeFalsy();
});

test('browser_run_code_unsafe with filename', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Clicked')">Click</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const code = 'await page.get_by_role("button", name="Click").click()';
  const filePath = test.info().outputPath('test-code.py');
  await fs.promises.writeFile(filePath, code);

  const response = parseResponse(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: { filename: 'test-code.py' },
  }));
  const content = await consoleEntries(response);
  expect(content).toContain('[LOG] Clicked');
});

test('browser_run_code_unsafe with filename containing template literals', async ({ client, server }) => {
  server.setContent('/', `
    <button onclick="console.log('Done')">Submit</button>
  `, 'text/html');
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.PREFIX },
  });

  const code = 'title = f"Page: {await page.title()}"\nawait page.get_by_role("button", name="Submit").click()\nreturn title';
  const filePath = test.info().outputPath('template-code.py');
  await fs.promises.writeFile(filePath, code);

  const response = parseResponse(await client.callTool({
    name: 'browser_run_code_unsafe',
    arguments: { filename: 'template-code.py' },
  }));
  const content = await consoleEntries(response);
  expect(content).toContain('[LOG] Done');
});
