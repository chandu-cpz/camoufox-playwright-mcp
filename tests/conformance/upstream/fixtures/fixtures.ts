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
import path from 'path';
import { fileURLToPath } from 'url';

import { test as baseTest, expect as baseExpect } from '@playwright/test';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { ListRootsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

import { TestServer } from './testserver/index.js';

import type { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import type { Stream } from 'stream';

export type TestOptions = {
  mcpArgs: string[] | undefined;
  mcpCaps: string[] | undefined;
  mcpBrowser: string | undefined;
};

export type StartClient = (options?: {
  clientName?: string;
  args?: string[];
  cwd?: string;
  config?: object | string;
  roots?: { name: string; uri: string }[];
  rootsResponseDelay?: number;
  env?: NodeJS.ProcessEnv;
  noTimeoutForTest?: boolean;
}) => Promise<{ client: Client; stderr: () => string }>;

type TestFixtures = {
  client: Client;
  startClient: StartClient;
  server: TestServer;
};

type WorkerFixtures = {
  _workerServer: TestServer;
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../../../');
const uvCommand = process.env.UV_BIN ?? (
  process.env.HOME ? path.join(process.env.HOME, '.local', 'bin', 'uv') : 'uv'
);

export const test = baseTest.extend<TestFixtures & TestOptions, WorkerFixtures>({
  mcpArgs: [undefined, { option: true }],
  mcpCaps: [undefined, { option: true }],
  mcpBrowser: [undefined, { option: true }],

  client: async ({ startClient }, use) => {
    const { client } = await startClient();
    await use(client);
  },

  startClient: async ({ mcpArgs, mcpCaps, mcpBrowser }, use, testInfo) => {
    const clients: Client[] = [];

    await use(async options => {
      let args = ['--headless', ...(mcpArgs ?? [])];
      if (mcpCaps?.length)
        args.push(`--caps=${mcpCaps.join(',')}`);
      if (mcpBrowser)
        args.push(`--browser=${mcpBrowser}`);
      if (options?.args)
        args.push(...options.args);

      if (options?.config) {
        const configFile = testInfo.outputPath('config.json');
        if (typeof options.config === 'object')
          await fs.promises.writeFile(configFile, JSON.stringify(options.config, null, 2));
        else
          await fs.promises.writeFile(configFile, options.config.trim());
        args.push(`--config=${configFile}`);
      }

      const client = new Client(
        { name: options?.clientName ?? 'test', version: '1.0.0' },
        options?.roots ? { capabilities: { roots: {} } } : undefined,
      );
      if (options?.roots) {
        client.setRequestHandler(ListRootsRequestSchema, async () => {
          if (options.rootsResponseDelay)
            await new Promise(resolve => setTimeout(resolve, options.rootsResponseDelay));
          return { roots: options.roots! };
        });
      }

      if (!options?.noTimeoutForTest && !args.some(arg => arg.startsWith('--timeout-action')))
        args.push('--timeout-action=10000');

      const { transport, stderr } = await createTransport(args, options?.cwd || testInfo.outputPath(), options?.env);
      let stderrBuffer = '';
      stderr?.on('data', data => {
        stderrBuffer += data.toString();
      });

      clients.push(client);
      await client.connect(transport);
      await client.ping();
      return { client, stderr: () => stderrBuffer };
    });

    await Promise.all(clients.map(client => client.close()));
  },

  _workerServer: [async ({}, use, workerInfo) => {
    const port = 8907 + workerInfo.workerIndex * 4;
    const server = await TestServer.create(port);
    server.reset();
    await use(server);
    await server.stop();
  }, { scope: 'worker' }],

  server: async ({ _workerServer }, use) => {
    _workerServer.reset();
    await use(_workerServer);
  },
});

async function createTransport(args: string[], cwd: string, env?: NodeJS.ProcessEnv): Promise<{
  transport: Transport;
  stderr: Stream | null;
}> {
  await fs.promises.mkdir(cwd, { recursive: true });

  const transport = new StdioClientTransport({
    command: uvCommand,
    args: ['run', '--project', repoRoot, 'playwright-python-mcp', ...args],
    cwd,
    stderr: 'pipe',
    env: {
      ...process.env,
      ...env,
      UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? '/tmp/uv-cache',
      DEBUG_COLORS: '0',
      DEBUG_HIDE_DATE: '1',
    },
  });
  return {
    transport,
    stderr: transport.stderr!,
  };
}

type Response = Awaited<ReturnType<Client['callTool']>>;

export const expect = baseExpect.extend({
  toHaveResponse(response: Response, object: any) {
    const parsed = parseResponse(response, test.info().outputPath());
    const text = parsed.text;
    const isNot = this.isNot;

    const keys = Object.keys(object);
    for (const key of Object.keys(parsed)) {
      if (!keys.includes(key))
        delete parsed[key];
    }

    try {
      if (isNot) {
        expect(parsed).not.toEqual(expect.objectContaining(object));
      } else {
        expect(parsed).toEqual(expect.objectContaining(object));
        if (parsed.isError && !object.isError)
          throw new Error('Response is an error, but expected is not');
      }
    } catch (e: any) {
      return {
        pass: isNot,
        message: () => e.message + '\n\nResponse text:\n' + text,
      };
    }
    return {
      pass: !isNot,
      message: () => ``,
    };
  },
});

export function parseResponse(response: any, cwd: string = test.info().outputPath()) {
  const text = response.content[0]?.type === 'text' ? response.content[0].text : '';
  const sections = parseSections(text);

  const snapshotSection = sections.get('Snapshot');
  let snapshot: string | undefined;
  if (snapshotSection) {
    const match = snapshotSection.match(/\[Snapshot\]\(([^)]+)\)/);
    if (match) {
      try {
        snapshot = fs.readFileSync(path.resolve(cwd, match[1]), 'utf-8');
      } catch {
        snapshot = undefined;
      }
    } else {
      snapshot = snapshotSection.replace(/^```yaml\n?/, '').replace(/\n?```$/, '');
    }
  }

  return {
    text,
    error: sections.get('Error'),
    result: sections.get('Result'),
    code: unwrapCodeBlock(sections.get('Ran Playwright code')),
    page: sections.get('Page'),
    snapshot,
    tabs: sections.get('Open tabs'),
    events: sections.get('Events'),
    modalState: sections.get('Modal state'),
    inlineSnapshot: snapshot,
    attachments: response.content?.slice(1),
    isError: response.isError,
  };
}

export async function consoleEntries(response: ReturnType<typeof parseResponse>) {
  const events = response.events;
  const match = events?.match(/New console entries: ([^\n]+)/);
  if (!match)
    return '';
  const file = match[1].replace(/#L\d+(-L\d+)?$/, '');
  try {
    return await fs.promises.readFile(path.resolve(test.info().outputPath(), file), 'utf-8');
  } catch {
    return '';
  }
}

function unwrapCodeBlock(value: string | undefined) {
  if (!value)
    return value;
  return value.replace(/^```[a-z]+\n/, '').replace(/\n```$/, '');
}

function parseSections(text: string): Map<string, string> {
  const sections = new Map<string, string>();
  const sectionHeaders = text.split(/^### /m).slice(1);

  for (const section of sectionHeaders) {
    const firstNewlineIndex = section.indexOf('\n');
    if (firstNewlineIndex === -1)
      continue;

    const sectionName = section.substring(0, firstNewlineIndex);
    const sectionContent = section.substring(firstNewlineIndex + 1).trim();
    sections.set(sectionName, sectionContent);
  }

  return sections;
}
