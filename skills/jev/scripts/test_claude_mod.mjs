import assert from 'node:assert/strict';
import test from 'node:test';
import { register, summarizeTask, modelCandidates } from '../claude/register.js';

const CANONICAL = { haiku: 'claude-haiku-test', sonnet: 'claude-sonnet-test',
  opus: 'claude-opus-test', fable: 'claude-fable-test' };

function host(options = {}) {
  const hooks = new Map();
  const calls = { processes: [], resolutions: [], logs: [], commands: [], env: 0, configs: 0 };
  let rows = options.rows ?? [{ key: 'model', kind: 'choice', isLocked: false,
    options: ['default', 'sonnet', 'opus', 'haiku', 'best', 'opusplan', 'opus[1m]'] }];
  let key = options.key === undefined ? 'synthetic-test-key' : options.key;
  const $ = {
    plugin: { root: '/test/plugin' },
    env: { get: async name => {
      assert.equal(name, 'JEV_API_KEY'); calls.env++; return key;
    } },
    command: {
      register: async spec => { calls.commands.push(spec); },
      list: async () => options.commands ?? [],
    },
    config: { list: async () => { calls.configs++; return rows; } },
    settings: { read: async () => options.settings ?? {} },
    session: { version: async () => ({ version: options.version ?? '2.1.296' }) },
    ui: { log: text => { calls.logs.push(text); } },
    process: { run: async (argv, init) => {
      if (argv[1].endsWith('/claude_models.py')) {
        calls.resolutions.push({ argv, init });
        if (options.resolveProcess) return options.resolveProcess(argv, init);
        const request = JSON.parse(init.stdin);
        return { exitCode: 0, stderr: '', stdout: JSON.stringify({ status: 'resolved',
          models: Object.fromEntries(request.aliases.map(alias => [alias, CANONICAL[alias]])) }) };
      }
      calls.processes.push({ argv, init });
      if (options.process) return options.process(argv, init);
      const request = JSON.parse(init.stdin);
      const scope = Object.keys(request.decisions)[0];
      return { exitCode: 0, stderr: '', stdout: JSON.stringify({
        status: 'recommended', decisions: { [scope]: {
          choice: options.choice ?? (scope === 'task' ? CANONICAL.haiku : 'haiku'), confidence: 0.9,
        } },
      }) };
    } },
  };
  register((name, matcher, hook) => {
    if (typeof matcher === 'function') hook = matcher;
    assert.ok(!hooks.has(name));
    hooks.set(name, hook);
    return { catch() {} };
  });
  let started = false;
  const event = (name, e, next = async input => input) => {
    if (name === 'session.start') started = true;
    if (name === 'session.end') started = false;
    return hooks.get(name)($, e, next);
  };
  const command = async (args, origin = 'composer', name = 'jev') => {
    if (!started) await event('session.start', {});
    return event('command.run', { command: name, args, origin: { kind: origin } });
  };
  return { $, calls, event, command, rows: value => { rows = value; }, key: value => { key = value; } };
}

async function stream(h, e, result = { usage: { model: 'claude-haiku-4-5' } }, fail) {
  const received = [], chunks = [{ kind: 'text', text: 'one' }, { kind: 'engine', ref: 3 }];
  let count = 0;
  const generator = h.event('turn.step', e, async function* (input) {
    count++; received.push(input);
    yield* chunks;
    if (fail) throw fail;
    return result;
  });
  const emitted = [];
  let item;
  do {
    item = await generator.next();
    if (!item.done) emitted.push(item.value);
  } while (!item.done);
  return { received, emitted, count, result: item.value, chunks };
}

test('session registers a native command and starts with all routing off', async () => {
  const h = host();
  await h.event('session.start', {});
  assert.equal(h.calls.commands[0].name, 'jev');
  const status = await h.command('status');
  assert.match(status.text, /task=off skill=off subagent=off/);
  assert.equal(h.calls.env, 0);
  assert.equal(h.calls.processes.length, 0);
});

test('an installed Jev skill is reused without a conflicting native registration', async () => {
  for (const command of [
    { name: 'jev', source: 'user', description: 'Jev routing for task models, skills, and subagent models. Use to configure routing.' },
    { name: 'jev', source: 'plugin', plugin: 'shuaigle', description: 'Jev' },
  ]) {
    const h = host({ commands: [command] });
    assert.match((await h.command('on task')).text, /task=on/);
    assert.equal(h.calls.commands.length, 0);
  }
});

test('an unrelated /jev command is preserved while /shuaigle:jev controls routing', async () => {
  const h = host({ commands: [{ name: 'jev', source: 'user', description: 'Manage my journal entries' }] });
  await h.event('session.start', {});
  let count = 0;
  const event = { command: 'jev', args: 'on all', origin: { kind: 'composer' } };
  const result = { text: 'Existing command output' };
  assert.equal(await h.event('command.run', event, async input => {
    count++; assert.equal(input, event); return result;
  }), result);
  assert.equal(count, 1);
  assert.equal(h.calls.commands.length, 0);
  assert.equal(h.calls.env, 0);
  assert.ok(h.calls.logs.some(text => text.includes('/shuaigle:jev')));
  assert.match((await h.command('status', 'composer', 'shuaigle:jev')).text, /task=off skill=off subagent=off/);
  assert.match((await h.command('on task', 'composer', 'shuaigle:jev')).text, /task=on/);
});

test('all seven enabled combinations and off scopes use session state', async () => {
  const names = ['task', 'skill', 'subagent'];
  for (let mask = 1; mask < 8; mask++) {
    const h = host();
    const chosen = names.filter((_, index) => mask & (1 << index));
    const result = await h.command(`on ${chosen.join(' ')}`);
    for (const name of names) assert.ok(result.text.includes(`${name}=${chosen.includes(name) ? 'on' : 'off'}`));
    await h.command('off');
    assert.match((await h.command('')).text, /task=off skill=off subagent=off/);
    assert.equal(h.calls.processes.length, 0);
  }
  const h = host();
  await h.command('on');
  assert.match((await h.command('status')).text, /task=on skill=off subagent=off/);
  await h.command('on all');
  await h.command('off task skill');
  assert.match((await h.command('status')).text, /task=off skill=off subagent=on/);
  await h.command('off all');
  assert.match((await h.command('status')).text, /task=off skill=off subagent=off/);
});

test('missing key and invalid controls preserve existing flags without leaking values', async () => {
  const h = host();
  await h.command('on skill');
  h.key('');
  assert.match((await h.command('on task')).text, /JEV_API_KEY/);
  assert.match((await h.command('status')).text, /task=off skill=on subagent=off/);
  const before = h.calls.env;
  for (const args of ['on bogus', 'off task bogus', 'status task', 'enable', 'on all task']) {
    assert.match((await h.command(args)).text, /Usage/);
    assert.match((await h.command('status')).text, /task=off skill=on subagent=off/);
  }
  assert.equal(h.calls.env, before);
  assert.ok(!JSON.stringify(h.calls.logs).includes('synthetic-test-key'));
});

test('only explicit user command origins may change flags', async () => {
  const h = host();
  for (const origin of ['plugin', 'peer', 'scheduled-trigger', 'observer', 'unclassified']) {
    const result = await h.command('on all', origin);
    assert.match(result.text, /user command/);
  }
  for (const origin of ['composer', 'bridge', 'sdk']) {
    await h.command('on task', origin, 'shuaigle:jev');
    assert.match((await h.command('status')).text, /task=on/);
    await h.command('off');
  }
  assert.equal(h.calls.env, 3);
});

test('sessions remain isolated and session end clears choices and flags', async () => {
  const a = host(), b = host();
  await a.command('on all');
  await a.event('turn.start', { turnId: 'a', text: 'Review changes' });
  assert.match((await b.command('status')).text, /task=off skill=off subagent=off/);
  await a.event('session.end', {});
  assert.match((await a.command('status')).text, /task=off skill=off subagent=off/);
  const result = await stream(a, { turnId: 'a', model: 'sonnet', index: 1 });
  assert.equal(result.received[0].model, 'sonnet');
});

test('disabled routing and skill-only routing make no model API calls', async () => {
  const h = host();
  await h.event('turn.start', { turnId: 'a', text: 'Implement this' });
  await h.event('agent.spawn', { prompt: 'Test', fork: false });
  await h.command('on skill');
  await h.event('turn.start', { turnId: 'b', text: 'Implement this' });
  await h.event('agent.spawn', { prompt: 'Test', fork: false });
  assert.equal(h.calls.processes.length, 0);
  const prompt = await h.event('prompt.submit', { text: 'Test', context: ['existing'] });
  assert.equal(prompt.context[0], 'existing');
  assert.match(prompt.context[1], /skill=on/);
  assert.match(prompt.context[1], /handled natively/);
  assert.match(prompt.context[1], /mandatory/);
});

test('candidate inventory uses current native options and excludes modes and private ids', () => {
  const candidates = modelCandidates([{ key: 'model', kind: 'choice', isLocked: false,
    options: ['default', 'sonnet', 'opus', 'haiku', 'fable', 'best', 'opusplan', 'sonnet[1m]',
      'claude-opus-4-6', 'arn:aws:private', '/private/model', 'custom/name', 'sonnet'] }]);
  assert.deepEqual(candidates.map(item => item.id), ['sonnet', 'opus', 'haiku', 'fable', 'claude-opus-4-6']);
  assert.deepEqual(modelCandidates([{ key: 'model', kind: 'choice', isLocked: true, options: ['sonnet'] }]), []);
  assert.deepEqual(modelCandidates([{ key: 'model', kind: 'text', options: ['sonnet'] }]), []);
});

test('feature summary never copies prompt text, paths, code, or secret strings', () => {
  const text = 'Review a complex concurrent payment upload with images. /private/project/client.js '
    + 'token-secret-xyz function privateAlgorithm() { return "secret"; }';
  const summary = summarizeTask(text);
  assert.match(summary, /review/);
  assert.match(summary, /concurrency/);
  assert.match(summary, /payments/);
  for (const value of ['token-secret-xyz', '/private/project', 'privateAlgorithm', 'client.js', text]) {
    assert.ok(!summary.includes(value));
  }
  assert.deepEqual(JSON.parse(summary).categories, ['review']);
});

test('a user turn routes once and every main step preserves its choice, chunks and result', async () => {
  const h = host();
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review changes' });
  await h.event('turn.start', { turnId: 'a', text: 'Review changes' });
  const result = { usage: { model: 'claude-haiku-4-5' }, answer: 'OK' };
  for (const index of [0, 1, 2]) {
    const got = await stream(h, { turnId: 'a', model: 'opus', effort: 'high', index }, result);
    assert.equal(got.received[0].model, CANONICAL.haiku);
    assert.equal(got.received[0].effort, 'high');
    assert.deepEqual(got.emitted, got.chunks);
    assert.equal(got.result, result);
    assert.equal(got.count, 1);
  }
  assert.equal(h.calls.processes.length, 1);
  assert.equal(h.calls.resolutions.length, 1);
  assert.deepEqual(JSON.parse(h.calls.resolutions[0].init.stdin), {
    aliases: ['sonnet', 'opus', 'haiku'], expected_version: '2.1.296',
  });
  assert.equal(h.calls.resolutions[0].init.timeoutMs, 6000);
  assert.equal(h.calls.logs.filter(line => line.includes('actual=claude-haiku-4-5')).length, 1);
  assert.ok(!h.calls.logs.some(line => /picker|default changed|session switched/.test(line)));
  const call = h.calls.processes[0];
  assert.deepEqual(call.argv, ['python3', '/test/plugin/skills/jev/scripts/route.py']);
  assert.equal(call.init.timeoutMs, 17000);
  assert.equal(call.init.env, undefined);
  assert.equal(call.init.stdin.includes('Review changes'), false);
  assert.deepEqual(Object.keys(JSON.parse(call.init.stdin).decisions), ['task']);
});

test('task aliases fail closed on resolver errors or unsafe IDs before calling Jev', async () => {
  for (const resolveProcess of [
    async () => { throw new Error('private secret'); },
    async () => ({ exitCode: 1, stdout: 'private secret', stderr: '' }),
    async () => ({ exitCode: 0, stdout: 'invalid JSON', stderr: '' }),
    async () => ({ exitCode: 0, stdout: JSON.stringify({ status: 'resolved',
      models: { haiku: 'haiku', sonnet: 'arn:aws:private', opus: '/private/model' } }), stderr: '' }),
  ]) {
    const h = host({ resolveProcess });
    await h.command('on task');
    await h.event('turn.start', { turnId: 'a', text: 'Review' });
    assert.equal((await stream(h, { turnId: 'a', model: 'sonnet' })).received[0].model, 'sonnet');
    assert.equal(h.calls.processes.length, 0);
    assert.ok(!JSON.stringify(h.calls.logs).includes('private secret'));
  }
});

test('canonical offered task models need no resolver and partial mappings omit unresolved aliases', async () => {
  const rows = [{ key: 'model', kind: 'choice', isLocked: false, options: [CANONICAL.haiku] }];
  const h = host({ rows });
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  assert.equal(h.calls.resolutions.length, 0);
  assert.equal((await stream(h, { turnId: 'a', model: 'opus' })).received[0].model, CANONICAL.haiku);
  const partial = host({ resolveProcess: async () => ({ exitCode: 0, stderr: '',
    stdout: JSON.stringify({ status: 'resolved', models: { haiku: CANONICAL.haiku } }) }) });
  await partial.command('on task');
  await partial.event('turn.start', { turnId: 'a', text: 'Review' });
  const choices = JSON.parse(partial.calls.processes[0].init.stdin).decisions.task;
  assert.deepEqual(choices.map(item => item.id), [CANONICAL.haiku]);
  assert.ok(!JSON.stringify(choices).includes('"id":"haiku"'));
  const mixed = host({ rows: [{ ...rows[0], options: [CANONICAL.haiku, 'sonnet'] }],
    resolveProcess: async () => { throw new Error('resolver unavailable'); } });
  await mixed.command('on task');
  await mixed.event('turn.start', { turnId: 'a', text: 'Review' });
  assert.equal((await stream(mixed, { turnId: 'a', model: 'opus' })).received[0].model, CANONICAL.haiku);
  assert.deepEqual(JSON.parse(mixed.calls.processes[0].init.stdin).decisions.task.map(item => item.id),
    [CANONICAL.haiku]);
});

test('an unresolved explicit task alias keeps the host model instead of choosing another one', async () => {
  const h = host({ resolveProcess: async () => ({ exitCode: 0, stderr: '',
    stdout: JSON.stringify({ status: 'resolved', models: { haiku: CANONICAL.haiku } }) }) });
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Use sonnet for this task: Review' });
  assert.equal((await stream(h, { turnId: 'a', model: 'opus' })).received[0].model, 'opus');
  assert.equal(h.calls.processes.length, 0);
});

test('each new turn gets live candidates and continuations reuse the latest successful choice', async () => {
  const h = host();
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  await h.event('turn.complete', { turnId: 'a' });
  await h.event('turn.start', { turnId: 'continuation', text: '' });
  assert.equal((await stream(h, { turnId: 'continuation', model: 'opus' })).received[0].model, CANONICAL.haiku);
  assert.equal(h.calls.processes.length, 1);
  h.rows([{ key: 'model', kind: 'choice', isLocked: false, options: ['opus', 'haiku'] }]);
  await h.event('turn.start', { turnId: 'b', text: 'Debug' });
  assert.equal(h.calls.configs, 2);
  const latest = JSON.parse(h.calls.processes[1].init.stdin);
  assert.deepEqual(latest.decisions.task.map(item => item.id), [CANONICAL.opus, CANONICAL.haiku]);
});

test('locked or unavailable models fall back visibly without an API request', async () => {
  for (const rows of [[], [{ key: 'model', kind: 'choice', isLocked: true, options: ['haiku'] }]]) {
    const h = host({ rows });
    await h.command('on task');
    await h.event('turn.start', { turnId: 'a', text: 'Review' });
    const got = await stream(h, { turnId: 'a', model: 'sonnet' });
    assert.equal(got.received[0].model, 'sonnet');
    assert.equal(h.calls.processes.length, 0);
    assert.ok(h.calls.logs.some(line => /unavailable|locked/.test(line)));
  }
});

test('effective availableModels restricts the live inventory without resolving unlisted aliases', async () => {
  const h = host({ settings: { availableModels: ['haiku'] } });
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  const request = JSON.parse(h.calls.processes[0].init.stdin);
  assert.deepEqual(request.decisions.task.map(item => item.id), [CANONICAL.haiku]);
  for (const availableModels of [[], ['claude-haiku-4-5'], 'haiku']) {
    const denied = host({ settings: { availableModels } });
    await denied.command('on task');
    await denied.event('turn.start', { turnId: 'a', text: 'Review' });
    assert.equal(denied.calls.processes.length, 0);
    assert.equal((await stream(denied, { turnId: 'a', model: 'sonnet' })).received[0].model, 'sonnet');
  }
});

test('unambiguous user task model clauses win without Jev, even if its key later disappears', async () => {
  for (const text of ['Use sonnet for this task: Review changes', '這個任務使用 sonnet：檢視改動']) {
    const h = host();
    await h.command('on task');
    h.key('');
    await h.event('turn.start', { turnId: 'a', text });
    assert.equal((await stream(h, { turnId: 'a', model: 'opus' })).received[0].model, CANONICAL.sonnet);
    assert.equal(h.calls.processes.length, 0);
  }
  for (const text of ['Review sonnet output', 'Use sonnet for this tasking example']) {
    const h = host();
    await h.command('on task');
    await h.event('turn.start', { turnId: 'a', text });
    assert.equal((await stream(h, { turnId: 'a', model: 'opus' })).received[0].model, CANONICAL.haiku);
    assert.equal(h.calls.processes.length, 1);
  }
});

test('subagent model selection routes only the existing planned child', async () => {
  const h = host();
  await h.command('on subagent');
  let count = 0, input;
  const spawn = { prompt: 'Debug concurrent failure /private/repo', description: 'Investigate',
    parentModel: 'opus', fork: false, tool_use_id: 't1', subagentType: 'Explore' };
  const result = { model: 'claude-haiku-4-5', agentId: 'child-1' };
  assert.equal(await h.event('agent.spawn', spawn, async e => { count++; input = e; return result; }), result);
  assert.equal(count, 1);
  assert.equal(input.model, 'haiku');
  assert.equal(input.prompt, spawn.prompt);
  assert.equal(input.subagentType, 'Explore');
  const request = JSON.parse(h.calls.processes[0].init.stdin);
  assert.deepEqual(Object.keys(request.decisions), ['subagent']);
  assert.match(request.task, /debug/);
  assert.ok(!request.task.includes('/private/repo'));
  assert.ok(h.calls.logs.some(line => line.includes('actual=claude-haiku-4-5')));
});

test('explicit child models and forks preserve their host inputs without routing', async () => {
  const h = host();
  await h.command('on subagent');
  for (const input of [{ prompt: 'Review', model: 'sonnet', fork: false }, { prompt: 'Review', fork: true }]) {
    let got;
    await h.event('agent.spawn', input, async e => { got = e; return { model: 'sonnet' }; });
    assert.equal(got, input);
  }
  assert.equal(h.calls.processes.length, 0);
  assert.ok(h.calls.logs.some(line => /fork/.test(line)));
});

test('main task routing never overrides child loop steps', async () => {
  const h = host();
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  const got = await stream(h, { turnId: 'a', model: 'sonnet', agentId: 'child' });
  assert.equal(got.received[0].model, 'sonnet');
});

test('process failures and invalid recommendations dispatch original event exactly once', async () => {
  for (const process of [
    async () => { throw new Error('secret-token /private/path'); },
    async () => ({ exitCode: 1, stdout: 'secret-token', stderr: '/private/path' }),
    async () => ({ exitCode: 0, stdout: 'not json', stderr: '' }),
    async () => ({ exitCode: 0, stdout: JSON.stringify({ status: 'recommended', decisions: {
      task: { choice: 'private/model', confidence: 1 }, subagent: { choice: 'private/model', confidence: 1 },
    } }), stderr: '' }),
  ]) {
    const h = host({ process });
    await h.command('on task subagent');
    await h.event('turn.start', { turnId: 'a', text: 'Review' });
    const got = await stream(h, { turnId: 'a', model: 'sonnet' });
    assert.equal(got.received[0].model, 'sonnet');
    assert.equal(got.count, 1);
    let count = 0;
    const spawn = { prompt: 'Review', fork: false };
    await h.event('agent.spawn', spawn, async input => { count++; assert.equal(input, spawn); });
    assert.equal(count, 1);
    assert.ok(!JSON.stringify(h.calls.logs).includes('secret-token'));
    assert.ok(!JSON.stringify(h.calls.logs).includes('/private/path'));
  }
});

test('downstream inference and spawn errors propagate without replay', async () => {
  const h = host();
  await h.command('on task subagent');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  let requests = 0;
  const error = new Error('host request failed');
  const generator = h.event('turn.step', { turnId: 'a', model: 'sonnet' }, async function* () {
    requests++; throw error;
  });
  await assert.rejects(generator.next(), error);
  assert.equal(requests, 1);
  let spawns = 0;
  await assert.rejects(h.event('agent.spawn', { prompt: 'Review', fork: false }, async () => {
    spawns++; throw error;
  }), error);
  assert.equal(spawns, 1);
});

test('turning task routing off clears pending overrides and continuation choices', async () => {
  const h = host();
  await h.command('on task');
  await h.event('turn.start', { turnId: 'a', text: 'Review' });
  await h.command('off task');
  assert.equal((await stream(h, { turnId: 'a', model: 'sonnet' })).received[0].model, 'sonnet');
  await h.command('on task');
  await h.event('turn.start', { turnId: 'continuation', text: '' });
  assert.equal((await stream(h, { turnId: 'continuation', model: 'sonnet' })).received[0].model, 'sonnet');
  assert.equal(h.calls.processes.length, 1);
});
