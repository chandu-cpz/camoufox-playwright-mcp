/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import fs from 'fs';

import { test, expect } from '../fixtures/fixtures.js';

test('browser_take_screenshot (viewport)', async ({ startClient, server }, testInfo) => {
  const { client } = await startClient({
    config: { outputDir: testInfo.outputPath('output') },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_take_screenshot',
  })).toHaveResponse({
    code: expect.stringContaining(`await page.screenshot`),
    attachments: [{
      data: expect.any(String),
      mimeType: 'image/png',
      type: 'image',
    }],
  });
});

test('browser_take_screenshot (element)', async ({ startClient, server }, testInfo) => {
  const { client } = await startClient({
    config: { outputDir: testInfo.outputPath('output') },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_take_screenshot',
    arguments: {
      element: 'hello button',
      target: 'e1',
    },
  })).toEqual(expect.objectContaining({
    content: [
      {
        text: expect.stringContaining(`page.get_by_text("Hello, world!").screenshot`),
        type: 'text',
      },
      {
        data: expect.any(String),
        mimeType: 'image/png',
        type: 'image',
      },
    ],
  }));
});

test('--output-dir should work', async ({ startClient, server }, testInfo) => {
  const outputDir = testInfo.outputPath('output');
  const { client } = await startClient({
    config: { outputDir },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  await client.callTool({
    name: 'browser_take_screenshot',
  });

  const files = [...fs.readdirSync(outputDir)].filter(f => f.endsWith('.png'));
  expect(files).toHaveLength(1);
  expect(files[0]).toMatch(/^page-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z\.png$/);
});

for (const type of ['png', 'jpeg'] as const) {
  test(`browser_take_screenshot (type: ${type})`, async ({ startClient, server }, testInfo) => {
    const outputDir = testInfo.outputPath('output');
    const { client } = await startClient({
      config: { outputDir },
    });
    await client.callTool({
      name: 'browser_navigate',
      arguments: { url: server.PREFIX },
    });

    expect(await client.callTool({
      name: 'browser_take_screenshot',
      arguments: { type },
    })).toEqual(expect.objectContaining({
      content: [
        {
          text: expect.stringMatching(new RegExp(`page-\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2}-\\d{2}\\-\\d{3}Z\\.${type}`)),
          type: 'text',
        },
        {
          data: expect.any(String),
          mimeType: `image/${type}`,
          type: 'image',
        },
      ],
    }));
  });
}

test('browser_take_screenshot (filename: "output.png")', async ({ client, server }, testInfo) => {
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_take_screenshot',
    arguments: {
      filename: 'output.png',
    },
  })).toEqual(expect.objectContaining({
    content: [
      {
        text: expect.stringContaining(`output.png`),
        type: 'text',
      },
    ],
  }));

  const files = [...fs.readdirSync(testInfo.outputPath())].filter(f => f.endsWith('.png'));
  expect(files).toEqual(['output.png']);
});

test('browser_take_screenshot (imageResponses=omit)', async ({ startClient, server }, testInfo) => {
  const { client } = await startClient({
    config: {
      outputDir: testInfo.outputPath('output'),
      imageResponses: 'omit',
    },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_take_screenshot',
  })).toEqual(expect.objectContaining({
    content: [
      {
        text: expect.stringContaining(`await page.screenshot`),
        type: 'text',
      },
    ],
  }));
});

test('browser_take_screenshot (fullPage: true)', async ({ startClient, server }, testInfo) => {
  const { client } = await startClient({
    config: { outputDir: testInfo.outputPath('output') },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  expect(await client.callTool({
    name: 'browser_take_screenshot',
    arguments: { fullPage: true },
  })).toEqual(expect.objectContaining({
    content: [
      {
        text: expect.stringContaining('full_page=True'),
        type: 'text',
      },
      {
        data: expect.any(String),
        mimeType: 'image/png',
        type: 'image',
      },
    ],
  }));
});

test('browser_take_screenshot (fullPage with element should error)', async ({ startClient, server }, testInfo) => {
  const { client } = await startClient({
    config: { outputDir: testInfo.outputPath('output') },
  });
  await client.callTool({
    name: 'browser_navigate',
    arguments: { url: server.HELLO_WORLD },
  });

  const result = await client.callTool({
    name: 'browser_take_screenshot',
    arguments: {
      fullPage: true,
      element: 'hello button',
      target: 'e1',
    },
  });

  expect(result.isError).toBe(true);
  expect(result.content?.[0]?.text).toContain('fullPage cannot be used with element screenshots');
});
