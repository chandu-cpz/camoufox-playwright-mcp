/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import { test, expect } from '../fixtures/fixtures.js';

test('cdp connection error returns MCP error response and can retry', async ({ startClient, server }) => {
  const { client } = await startClient({ args: [`--cdp-endpoint=${server.PREFIX}`] });

  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    isError: true,
    error: expect.stringContaining('Unexpected status'),
  });

  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    isError: true,
  });
});

test('cdp alias sends headers', async ({ startClient, server }) => {
  let authHeader = '';
  server.setRoute('/json/version/', (req, res) => {
    authHeader = req.headers['authorization'] as string;
    res.end();
  });

  const { client } = await startClient({ args: [`--cdp=${server.PREFIX}`, '--cdp-header', 'Authorization: Bearer 1234567890'] });
  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    isError: true,
  });
  expect(authHeader).toBe('Bearer 1234567890');
});

test('cdp server with empty and complex headers', async ({ startClient, server }) => {
  let customHeader = '';
  let emptyHeader = '';
  server.setRoute('/json/version/', (req, res) => {
    customHeader = req.headers['x-forwarded-proto'] as string;
    emptyHeader = req.headers['x-empty'] as string;
    res.end();
  });

  const { client } = await startClient({
    args: [
      `--cdp-endpoint=${server.PREFIX}`,
      '--cdp-header', 'X-Forwarded-Proto: value:with:colons',
      '--cdp-header', 'X-Empty',
    ],
  });
  expect(await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  })).toHaveResponse({
    isError: true,
  });
  expect(customHeader).toBe('value:with:colons');
  expect(emptyHeader).toBe('');
});
