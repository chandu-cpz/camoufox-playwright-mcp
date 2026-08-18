/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import fs from 'fs';

import { test, expect } from '../fixtures/fixtures.js';

test('save as pdf unavailable', async ({ startClient, server }) => {
  const { client } = await startClient();
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_pdf_save',
  })).toHaveResponse({
    error: undefined,
    isError: true,
  });
});

test('save as pdf', async ({ startClient, mcpBrowser, server }, testInfo) => {
  test.skip(!!mcpBrowser && !['chromium', 'chrome', 'msedge'].includes(mcpBrowser), 'Save as PDF is only supported in Chromium.');
  const { client } = await startClient({
    config: { outputDir: testInfo.outputPath('output'), capabilities: ['pdf'] },
  });

  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    snapshot: expect.stringContaining(`- generic [active] [ref=e1]: Hello, world!`),
  });

  expect(await client.callTool({
    name: 'browser_pdf_save',
  })).toHaveResponse({
    code: expect.stringContaining(`await page.pdf(`),
    result: expect.stringMatching(/\[Page as pdf\]\(.*page-[^:]+.pdf\)/),
  });
});

test('save as pdf (filename: output.pdf)', async ({ startClient, mcpBrowser, server }, testInfo) => {
  test.skip(!!mcpBrowser && !['chromium', 'chrome', 'msedge'].includes(mcpBrowser), 'Save as PDF is only supported in Chromium.');
  const { client } = await startClient({
    config: { capabilities: ['pdf'] },
  });

  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    snapshot: expect.stringContaining(`- generic [active] [ref=e1]: Hello, world!`),
  });

  expect(await client.callTool({
    name: 'browser_pdf_save',
    arguments: {
      filename: 'output.pdf',
    },
  })).toHaveResponse({
    result: expect.stringContaining(`output.pdf`),
    code: expect.stringContaining(`await page.pdf(`),
  });

  const files = [...fs.readdirSync(testInfo.outputPath())];
  expect(files.filter(f => f.endsWith('.pdf'))).toEqual(['output.pdf']);
});
