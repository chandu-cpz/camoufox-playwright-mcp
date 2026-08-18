/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import { test, expect, parseResponse } from '../fixtures/fixtures.js';

test.use({ mcpCaps: ['config'] });

test('browser_get_config returns resolved server config', async ({ client }) => {
  const result = await client.callTool({
    name: 'browser_get_config',
  });

  expect(result.isError).toBeFalsy();
  const parsed = parseResponse(result);
  const config = JSON.parse(parsed.result);

  expect(config.browser).toBeTruthy();
  expect(config.capabilities ?? config.caps).toContain('config');
  expect(config.codegen).toBe('python');
});

test('browser_get_config returns merged config from file, env and cli', async ({ startClient }) => {
  const { client } = await startClient({
    config: {
      browser: {
        contextOptions: {
          viewport: { width: 800, height: 600 },
        },
      },
      capabilities: ['config'],
      timeouts: {
        action: 10000,
        navigation: 30000,
      },
    },
    args: ['--isolated'],
    env: {
      PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION: '45000',
    },
  });

  const result = await client.callTool({
    name: 'browser_get_config',
  });

  expect(result.isError).toBeFalsy();
  const parsed = parseResponse(result);
  const config = JSON.parse(parsed.result);

  expect(config.browser.contextOptions.viewport).toEqual({ width: 800, height: 600 });
  expect(config.timeouts.action).toBe(10000);
  expect(config.timeouts.navigation).toBe(45000);
  expect(config.browser.isolated).toBe(true);
});
