/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import { spawn, type ChildProcessWithoutNullStreams } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { test, expect } from '../fixtures/fixtures.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../../../');
const uvCommand = process.env.UV_BIN ?? (
  process.env.HOME ? path.join(process.env.HOME, '.local', 'bin', 'uv') : 'uv'
);

test('serves streamable HTTP on --port and --host', async ({}, testInfo) => {
  const port = 9300 + testInfo.workerIndex;
  const server = await startHttpServer(port, ['--allowed-hosts=localhost']);
  const client = new Client({ name: 'http-test', version: '1.0.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(`http://localhost:${port}/mcp`)));
  try {
    const tools = await client.listTools();
    expect(tools.tools.some(tool => tool.name === 'browser_navigate')).toBeTruthy();
  } finally {
    await client.close();
    await stopServer(server);
  }
});

test('rejects disallowed HTTP Host header', async ({}, testInfo) => {
  const port = 9400 + testInfo.workerIndex;
  const server = await startHttpServer(port, ['--allowed-hosts=allowed.example']);
  try {
    const response = await fetch(`http://localhost:${port}/mcp`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'host': 'blocked.example',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} }),
    });
    expect(response.status).toBe(403);
    expect(await response.text()).toContain('Host is not allowed');
  } finally {
    await stopServer(server);
  }
});

async function startHttpServer(port: number, extraArgs: string[] = []): Promise<ChildProcessWithoutNullStreams> {
  const server = spawn(uvCommand, [
    'run',
    '--project',
    repoRoot,
    'playwright-python-mcp',
    '--headless',
    `--port=${port}`,
    '--host=127.0.0.1',
    ...extraArgs,
  ], {
    cwd: repoRoot,
    env: {
      ...process.env,
      UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? '/tmp/uv-cache',
      DEBUG_COLORS: '0',
      DEBUG_HIDE_DATE: '1',
    },
  });

  let stderr = '';
  server.stderr.on('data', data => stderr += data.toString());
  server.stdout.on('data', () => {});
  await expect.poll(async () => {
    if (server.exitCode !== null)
      throw new Error(`Server exited early with code ${server.exitCode}\n${stderr}`);
    try {
      const response = await fetch(`http://localhost:${port}/mcp`, { method: 'GET' });
      return response.status;
    } catch {
      return 0;
    }
  }, { timeout: 10000 }).not.toBe(0);
  return server;
}

async function stopServer(server: ChildProcessWithoutNullStreams): Promise<void> {
  if (server.exitCode !== null)
    return;
  server.kill();
  await new Promise<void>(resolve => server.once('exit', () => resolve()));
}
