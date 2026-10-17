import assert from 'node:assert/strict';
import test from 'node:test';
import { register, summarizeTask, modelCandidates } from '../claude/register.js';
import { readFileSync } from 'node:fs';

function host(options = {}) {
  const hooks = new Map();
  const matchers = new Map();
  const calls = { processes: [], logs: [], commands: [], env: 0, configs: 0, sleeps: [] };
  let rows = options.rows ?? [{ key: 'model', kind: 'choice', isLocked: false,
    options: ['default', 'sonnet', 'opus', 'haiku', 'best', 'opusplan', 'opus[1m]'] }];
  let key = options.key === undefined ? 'synthetic-test-key' : options.key;
  const $ = {
    plugin: { root: '/test/plugin' },
    env: { get: async name => {
      if (name === 'CLAUDE_CODE_EFFORT_LEVEL') return options.effortEnv;
      assert.equal(name, 'JEV_API_KEY'); calls.env++; return key;
    } },
    clock: { sleep: ms => { calls.sleeps.push(ms); return options.sleep ? options.sleep(ms) : new Promise(() => {}); } },
    command: { register: async spec => { calls.commands.push(spec); }, list: async () => options.commands ?? [] },
    config: { list: async () => { calls.configs++; return rows; } },
    settings: { read: async () => options.settings ?? {} },
    ui: { log: text => { calls.logs.push(text); } },
    process: { run: async (argv, init) => {
      calls.processes.push({ argv, init });
      if (options.process) return options.process(argv, init);
      const candidates = JSON.parse(init.stdin).decisions.subagent;
      const selected = candidates.find(item => item.model === (options.choice ?? 'haiku')
        && (options.effort === undefined || item.effort === options.effort));
      return { exitCode: 0, stderr: '', stdout: JSON.stringify({ status: 'recommended',
        decisions: { subagent: { choice: selected.id, model: selected.model, effort: selected.effort,
          confidence: 0.9 } } }) };
    } },
  };
  register((name, matcher, hook) => {
    if (typeof matcher === 'function') { hook = matcher; matcher = {}; }
    matchers.set(name, matcher);
    assert.ok(!hooks.has(name)); hooks.set(name, hook); return { catch() {} };
  });
  let started = false;
  const event = (name, e, next = async input => input) => {
    if (name === 'session.start') started = true;
    if (name === 'session.end') started = false;
    const matches = Object.entries(matchers.get(name) ?? {}).every(([field, expected]) =>
      Array.isArray(expected) ? expected.includes(e[field])
        : expected instanceof RegExp ? expected.test(e[field]) : e[field] === expected);
    return hooks.has(name) && matches ? hooks.get(name)($, e, next) : next(e);
  };
  const command = async (args, origin = 'composer', name = 'jev') => {
    if (!started) await event('session.start', {});
    return event('command.run', { command: name, args, origin: { kind: origin } });
  };
  return { $, hooks, calls, event, command, rows: value => { rows = value; }, key: value => { key = value; } };
}

function child(id = 'spawn-1', extra = {}) {
  return { tool_use_id: id, prompt: 'Review a concurrent change', description: 'Inspect',
    parentModel: 'sonnet', subagentType: 'Explore', fork: false, ...extra };
}

async function spawn(h, e = child(), actual = 'claude-haiku-test') {
  let input, count = 0;
  const output = { model: actual, agentId: 'child-id' };
  const result = await h.event('agent.spawn', e, async value => { input = value; count++; return output; });
  assert.equal(result, output); assert.equal(count, 1);
  return input;
}

// Runs the parent's Agent tool call around its spawn, as the host does.
async function agentCall(h, e, args, inner = () => spawn(h, e)) {
  return h.event('tool.call', { tool: 'Agent', tool_use_id: e.tool_use_id, agentId: e.parentAgentId,
    description: e.description, prompt: e.prompt, ...args }, inner);
}

// Drives one turn.step generator; returns the request it sent down and the result.
async function step(h, e) {
  const sent = [];
  const body = h.event('turn.step', e, async function* (input) {
    sent.push(input); yield { kind: 'text', text: 'ok' };
    return { turnId: input.turnId, index: input.index, answer: 'ok', toolUses: [] };
  });
  const chunks = [];
  let item;
  while (!(item = await body.next()).done) chunks.push(item.value);
  assert.deepEqual(chunks, [{ kind: 'text', text: 'ok' }]);
  assert.equal(sent.length, 1);
  return { sent: sent[0], result: item.value };
}

function stepEvent(agentId, extra = {}) {
  return { turnId: 'turn', index: 0, model: 'claude-haiku-test', effort: 'high', messageCount: 1,
    ...(agentId === undefined ? {} : { agentId }), ...extra };
}

const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'];
const models = candidates => [...new Set(candidates.map(item => item.model))];

const allOff = /skill=off subagent=off/;
const allOn = /skill=on subagent=on/;

test('the engine can list every environment variable the module reads', () => {
  const source = readFileSync(new URL('../claude/register.js', import.meta.url), 'utf8');
  const reads = [...source.matchAll(/\$\.env\.get\(([^)]*)\)/g)].map(match => match[1]);
  assert.ok(reads.length);
  for (const name of reads) assert.match(name, /^'[A-Z_]+'$/);
});

test('a human exclusion blocks later combined spawns in this conversation', async () => {
  const h = host();
  await h.command('on all');
  const excluded = await h.command('exclude fable');
  assert.match(excluded.context[0], /Manually excluded models in this conversation: fable/);
  assert.match(excluded.context[0], /Only explicit human exclude\/include commands change this list/);
  let dispatches = 0;
  const result = await h.event('agent.spawn', child('another-child', { model: 'fable' }),
    async e => { dispatches++; return { model: e.model, agentId: 'unexpected-start' }; });
  assert.equal(dispatches, 0, 'a manually excluded model must not start another child');
  assert.match(result.deny, /fable.*unavailable|unavailable.*fable/i);
  assert.equal(h.calls.processes.length, 0, 'manual exclusions must not add Jev requests');
});

test('native session registers controls with all decisions off and no API access', async () => {
  const h = host();
  await h.event('session.start', {});
  assert.equal(h.calls.commands[0].name, 'jev');
  assert.match(h.calls.commands[0].argumentHint, /skill subagent/);
  assert.ok(!h.calls.commands[0].argumentHint.includes('task'));
  assert.match((await h.command('status')).text, allOff);
  assert.equal(h.calls.env, 0); assert.equal(h.calls.processes.length, 0);
});

test('bare on and on all enable both supported decisions', async () => {
  for (const args of ['on', 'on all', 'on skill subagent']) {
    const h = host();
    assert.match((await h.command(args)).text, allOn);
    assert.equal(h.calls.processes.length, 0);
    await h.command('off skill');
    assert.match((await h.command('status')).text, /skill=off subagent=on/);
    await h.command('off subagent');
    assert.match((await h.command('')).text, allOff);
    await h.command('on');
    await h.command('off all');
    assert.match((await h.command('status')).text, allOff);
  }
});

test('task controls and invalid arguments leave flags unchanged', async () => {
  const h = host();
  await h.command('on skill');
  const envReads = h.calls.env;
  for (const args of ['on task', 'off task', 'on skill task', 'off task skill', 'status task', 'on all skill', 'enable']) {
    assert.match((await h.command(args)).text, /Usage/);
    assert.match((await h.command('status')).text, /skill=on subagent=off/);
  }
  assert.equal(h.calls.env, envReads);
  assert.equal(h.calls.processes.length, 0);
});

test('a missing key preserves enabled decisions and prints no key value', async () => {
  const h = host();
  await h.command('on skill'); h.key('');
  assert.match((await h.command('on subagent')).text, /JEV_API_KEY/);
  assert.match((await h.command('status')).text, /skill=on subagent=off/);
  assert.ok(!JSON.stringify(h.calls.logs).includes('synthetic-test-key'));
});

test('only explicit human-origin commands can enable or disable routing', async () => {
  const h = host();
  for (const origin of ['plugin', 'peer', 'scheduled-trigger', 'observer', 'unclassified']) {
    assert.match((await h.command('on all', origin)).text, /user command/);
    assert.match((await h.command('status')).text, allOff);
  }
  for (const origin of ['composer', 'bridge', 'sdk']) {
    assert.match((await h.command('on', origin, 'shuaigle:jev')).text, allOn);
    assert.match((await h.command('off', 'plugin')).text, /user command/);
    assert.match((await h.command('status')).text, allOn);
    await h.command('off');
  }
  assert.equal(h.calls.env, 3);
});

test('installed new and old Jev skills reuse the command without conflicting registration', async () => {
  for (const entry of [
    { name: 'jev', source: 'user', description: 'Jev routing for optional skills and subagent model/effort pairs.' },
    { name: 'jev', source: 'user', description: 'Jev routing for optional skills and subagent models.' },
    { name: 'jev', source: 'user', description: 'Jev routing for task models, skills, and subagent models.' },
    { name: 'jev', source: 'plugin', plugin: 'shuaigle', description: 'Jev' },
  ]) {
    const h = host({ commands: [entry] });
    assert.match((await h.command('on subagent')).text, /subagent=on/);
    assert.equal(h.calls.commands.length, 0);
    assert.match((await h.command('on task')).text, /Usage/);
  }
});

test('an unrelated bare command is preserved while namespaced controls remain available', async () => {
  const h = host({ commands: [{ name: 'jev', source: 'user', description: 'Manage journal entries' }] });
  await h.event('session.start', {});
  const e = { command: 'jev', args: 'on all', origin: { kind: 'composer' } };
  const output = { text: 'Existing output' }; let count = 0;
  assert.equal(await h.event('command.run', e, async input => { count++; assert.equal(input, e); return output; }), output);
  assert.equal(count, 1); assert.equal(h.calls.env, 0); assert.equal(h.calls.commands.length, 0);
  assert.ok(h.calls.logs.some(text => text.includes('/shuaigle:jev')));
  assert.match((await h.command('status', 'composer', 'shuaigle:jev')).text, allOff);
  assert.match((await h.command('on', 'composer', 'shuaigle:jev')).text, allOn);
});

test('all-off and skill-only native behavior make no model requests', async () => {
  const h = host();
  await h.event('session.start', {});
  const e = child(); assert.equal(await spawn(h, e, 'sonnet'), e);
  await h.command('on skill');
  assert.equal(await spawn(h, child('skill-only'), 'sonnet').then(value => value.model), undefined);
  const submitted = { text: 'Read and summarize', context: ['existing'] };
  const prompt = await h.event('prompt.submit', submitted);
  assert.equal(prompt.text, submitted.text); assert.equal(prompt.context[0], 'existing');
  assert.match(prompt.context[1], /skill=on subagent=off/);
  assert.match(prompt.context[1], /zero or more optional skills once per/);
  assert.match(prompt.context[1], /including failures.*continuations/);
  assert.match(prompt.context[1], /mandatory skill rules/);
  assert.equal(h.calls.processes.length, 0);
});

test('combined skill and subagent routing uses one agent-prepared batch without a native request', async () => {
  const h = host(); await h.command('on');
  const prepared = child('prepared', { model: 'haiku', prompt: 'Review; prepared skills: testing, security' });
  assert.equal(await spawn(h, prepared), prepared);
  const fallback = child('fallback');
  assert.equal(await spawn(h, fallback, 'sonnet'), fallback);
  assert.equal(await spawn(h, { ...fallback }, 'sonnet').then(value => value.model), undefined);
  assert.equal(h.calls.processes.length, 0); assert.equal(h.calls.configs, 0);
  assert.equal(h.calls.logs.filter(text => text.includes('unset model keeps inheritance')).length, 1);
  const prompt = await h.event('prompt.submit', { text: 'Continue the child work' });
  assert.match(prompt.context[0], /one combined Jev batch per child unit/);
  assert.match(prompt.context[0], /native hook never reroutes this combined path/);
  assert.match(prompt.context[0], /report effort-routing unavailable/);
  assert.match(prompt.context[0], /keep model and skill decisions in that same batch/);
  assert.match(prompt.context[0], /effort:null means omit Agent.effort and use host-controlled effort/);
  assert.ok(!prompt.context[0].includes('reuse ordinary fallback for the unit instead of asking Jev'));
  assert.match(prompt.context[0], /concrete effort is this skill's explicit per-invocation instruction/);
  await h.command('off skill');
  assert.equal(await spawn(h, fallback, 'sonnet'), fallback);
  assert.equal(h.calls.processes.length, 0);
  assert.equal((await spawn(h, child('new-native-child'))).model, 'haiku');
  assert.equal(h.calls.processes.length, 1);
});

test('main-turn events keep the model, effort and dispatch unchanged', async () => {
  const h = host({ effort: 'low' }); await h.command('on subagent');
  for (const name of ['turn.start', 'turn.complete']) {
    assert.equal(h.hooks.has(name), false);
    const e = { turnId: 'main', text: 'Use another model', model: 'opus', effort: 'max' };
    const got = await h.event(name, e);
    assert.equal(got, e); assert.equal(got.model, 'opus'); assert.equal(got.effort, 'max');
  }
  await spawn(h);
  const main = stepEvent(undefined, { model: 'opus', effort: 'max' });
  const { sent, result } = await step(h, main);
  assert.equal(sent, main); assert.equal(result.answer, 'ok');
  const unknown = stepEvent('another-child');
  assert.equal((await step(h, unknown)).sent, unknown);
  assert.equal(h.calls.processes.length, 1); assert.equal(h.calls.sleeps.length, 0);
});

test('turn.step applies the selected effort to every model request of the routed child', async () => {
  const h = host({ effort: 'xhigh' }); await h.command('on subagent');
  await spawn(h);
  for (const index of [0, 1, 2]) {
    const e = stepEvent('child-id', { index });
    const { sent, result } = await step(h, e);
    assert.deepEqual(sent, { ...e, effort: 'xhigh' }); assert.equal(result.index, index);
  }
  assert.equal(h.calls.logs.filter(text => text.includes('effort requested=xhigh actual=unverified')).length, 1);
  assert.match((await h.command('status')).text,
    /effort requested=xhigh actual=unverified \(the host lowers an unsupported effort without reporting it\)/);
  assert.ok(!(await h.command('status')).text.includes('applied'));
});

test('a child model without effort is sent none and reports that actual effort', async () => {
  const h = host({ effort: 'low' }); await h.command('on subagent'); await spawn(h);
  const e = stepEvent('child-id', { effort: undefined }); delete e.effort;
  assert.equal((await step(h, e)).sent, e);
  assert.match((await h.command('status')).text, /effort requested=low actual=none \(the model takes no effort\)/);
});

test('CLAUDE_CODE_EFFORT_LEVEL locks effort: model-only candidates and no step rewrite', async () => {
  const h = host({ effortEnv: 'medium' }); await h.command('on subagent');
  assert.equal((await spawn(h)).model, 'haiku');
  const candidates = JSON.parse(h.calls.processes[0].init.stdin).decisions.subagent;
  assert.deepEqual(candidates.map(item => item.effort), [null, null, null]);
  const e = stepEvent('child-id', { effort: 'medium' });
  assert.equal((await step(h, e)).sent, e);
  assert.ok(h.calls.logs.some(text => text.includes('effort locked by CLAUDE_CODE_EFFORT_LEVEL')));
  assert.match((await h.command('status')).text, /effort locked by CLAUDE_CODE_EFFORT_LEVEL/);
});

test('a child step that arrives before its spawn answers waits for the effort mapping', async () => {
  const h = host({ effort: 'max' }); await h.command('on subagent');
  let answer;
  const dispatched = h.event('agent.spawn', child(), async () => new Promise(done => { answer = done; }));
  while (!answer) await new Promise(done => setImmediate(done));
  const early = step(h, stepEvent('child-id'));
  await new Promise(done => setImmediate(done));
  assert.deepEqual(h.calls.sleeps, [3000]);
  answer({ model: 'claude-haiku-test', agentId: 'child-id' });
  assert.equal((await early).sent.effort, 'max');
  await dispatched;
  const timedOut = host({ effort: 'max', sleep: async () => {} }); await timedOut.command('on subagent');
  timedOut.event('agent.spawn', child(), async () => new Promise(() => {}));
  await new Promise(done => setImmediate(done));
  const e = stepEvent('slow-child');
  assert.equal((await step(timedOut, e)).sent, e);
});

test('a resumed child keeps its agentId and its selected effort', async () => {
  const h = host({ effort: 'low' }); await h.command('on subagent'); await spawn(h);
  const resume = child('resume-call', { resume: { agentId: 'child-id' } });
  let resumed;
  await h.event('agent.spawn', resume, async input => { resumed = input; return { model: 'claude-haiku-test', agentId: 'child-id' }; });
  assert.equal(resumed, resume);
  assert.equal((await step(h, stepEvent('child-id', { index: 5 }))).sent.effort, 'low');
  assert.equal(h.calls.processes.length, 1);
});

test('a spawn without a stable ID routes the model only', async () => {
  const h = host(); await h.command('on subagent');
  await spawn(h, child(undefined, { tool_use_id: undefined }));
  const candidates = JSON.parse(h.calls.processes[0].init.stdin).decisions.subagent;
  assert.ok(candidates.every(item => item.effort === null));
  assert.equal((await step(h, stepEvent('child-id'))).sent.effort, 'high');
});

test('one stable spawn routes once and reuses its choice through repeated dispatches', async () => {
  const h = host(); await h.command('on subagent');
  const e = child();
  assert.equal((await spawn(h, e)).model, 'haiku');
  assert.equal((await spawn(h, { ...e })).model, 'haiku');
  assert.equal(h.calls.processes.length, 1); assert.equal(h.calls.configs, 1);
  assert.equal(h.calls.logs.filter(text => text.includes('actual=claude-haiku-test')).length, 1);
  const call = h.calls.processes[0];
  assert.deepEqual(call.argv, ['python3', '/test/plugin/skills/jev/scripts/route.py']);
  assert.equal(call.init.timeoutMs, 17000); assert.equal(call.init.env, undefined);
  const request = JSON.parse(call.init.stdin);
  assert.deepEqual(Object.keys(request.decisions), ['subagent']);
  assert.equal(request.current_model, undefined); assert.equal(request.models, undefined);
  assert.ok(!call.init.stdin.includes(e.prompt));
});

test('native candidates are atomic model/effort options with opaque IDs', async () => {
  const h = host({ effort: 'medium' }); await h.command('on subagent');
  const applied = await spawn(h);
  assert.equal(applied.model, 'haiku'); assert.equal(Object.hasOwn(applied, 'effort'), false);
  const candidates = JSON.parse(h.calls.processes[0].init.stdin).decisions.subagent;
  assert.deepEqual(candidates.map(item => [item.model, item.effort]),
    ['sonnet', 'opus', 'haiku'].flatMap(model => EFFORTS.map(effort => [model, effort])));
  for (const item of candidates) {
    assert.deepEqual(Object.keys(item).sort(), ['description', 'effort', 'id', 'model']);
    assert.notEqual(item.id, item.model); assert.match(item.description, /lowers or drops/);
  }
  assert.ok(h.calls.logs.some(text => text.includes('effort requested=medium actual=awaiting first request')));
  assert.match((await h.command('status')).text, /effort requested=medium actual=awaiting first request/);
  const prompt = await h.event('prompt.submit', { text: 'Continue' });
  assert.ok(!prompt.context[0].includes('no verified per-spawn effort control'));
  assert.match(prompt.context[0], /Native candidates pair each offered model with low, medium, high, xhigh and max/);
  assert.match(prompt.context[0], /CLAUDE_CODE_EFFORT_LEVEL/);
});

test('native candidates use every effort level per model regardless of the session effort row', () => {
  const candidates = modelCandidates([
    { key: 'model', kind: 'choice', isLocked: false, value: 'sonnet', options: ['sonnet', 'haiku'] },
    { key: 'effort', kind: 'choice', isLocked: false, value: 'max', options: ['low', 'max'] },
  ]);
  assert.deepEqual(candidates.map(item => [item.model, item.effort]),
    ['sonnet', 'haiku'].flatMap(model => EFFORTS.map(effort => [model, effort])));
  assert.deepEqual(modelCandidates([{ key: 'model', kind: 'choice', isLocked: false, options: ['haiku'] }],
    undefined, new Set(), [null]).map(item => item.effort), [null]);
});

test('a recommendation cannot substitute a model or effort outside the chosen atomic option', async () => {
  for (const subagent of [
    { choice: 'subagent-2', model: 'opus', effort: null, confidence: 0.9 },
    { choice: 'subagent-2', model: 'haiku', effort: 'low', confidence: 0.9 },
    { choice: 'haiku', model: 'haiku', effort: null, confidence: 0.9 },
    { choice: 'subagent-10', model: 'haiku', effort: 'max', confidence: 0.9 },
    { choice: 'subagent-10', model: 'haiku', effort: null, confidence: 0.9 },
  ]) {
    const h = host({ process: async () => ({ exitCode: 0, stderr: '', stdout: JSON.stringify({
      status: 'recommended', decisions: { subagent } }) }) });
    await h.command('on subagent'); const e = child();
    assert.equal(await spawn(h, e, 'sonnet'), e);
    assert.equal(await spawn(h, e, 'sonnet'), e);
    assert.equal(h.calls.processes.length, 1);
  }
});

test('explicit effort remains unchanged without guessing a compatible model', async () => {
  const h = host(); await h.command('on subagent');
  const e = child('explicit-effort');
  assert.equal(await agentCall(h, e, { effort: 'low' }, () => spawn(h, e, 'sonnet')), e);
  assert.equal(h.calls.processes.length, 0);
  const own = stepEvent('child-id', { effort: 'low' });
  assert.equal((await step(h, own)).sent, own);
  assert.ok(h.calls.logs.some(text => text.includes('explicit effort has no verified compatible model inventory')));
  const prompt = await h.event('prompt.submit', { text: 'Continue with my fixed effort' });
  assert.match(prompt.context[0], /user fixed effort and compatible models cannot be verified/);
  assert.match(prompt.context[0], /preserve the original model and that effort, route only optional skills/);
  assert.match(prompt.context[0], /never replace the user's value with null/);
  const continuation = child('explicit-effort');
  assert.equal(await spawn(h, continuation, 'sonnet'), continuation);
  assert.equal(h.calls.processes.length, 0);
  await h.command('on skill');
  const prepared = child('prepared-pair', { model: 'haiku' });
  assert.equal(await agentCall(h, prepared, { model: 'haiku', effort: 'medium' }), prepared);
  assert.equal(h.calls.processes.length, 0);
});

test('only the Agent tool call reveals explicit effort; the spawn input has no effort field', async () => {
  const h = host({ effort: 'max' }); await h.command('on subagent');
  const other = { tool: 'Read', tool_use_id: 'spawn-1', file_path: 'note.txt', effort: 'low' };
  assert.equal(await h.event('tool.call', other), other);
  assert.equal((await spawn(h)).model, 'haiku');
  assert.equal(h.calls.processes.length, 1);
  assert.equal((await step(h, stepEvent('child-id'))).sent.effort, 'max');
  const nested = child('nested', { parentAgentId: 'child-id' });
  assert.equal(await agentCall(h, nested, { effort: 'low' }, () => spawn(h, nested, 'sonnet')), nested);
  assert.equal(h.calls.processes.length, 1);
});

test('combined default-effort preparation preserves model and skills without a second routing call', async () => {
  const h = host(); await h.command('on');
  const prepared = child('combined-default', { model: 'haiku', prompt: 'Prepared skills: testing, security' });
  assert.equal(await spawn(h, prepared), prepared);
  assert.equal(await spawn(h, { ...prepared }).then(value => value.model), 'haiku');
  assert.equal(h.calls.processes.length, 0);
  assert.equal(h.calls.configs, 0);
  assert.equal(Object.hasOwn(prepared, 'effort'), false);
  await h.command('off skill');
  assert.equal((await spawn(h, child('combined-default'))).model, 'haiku');
  assert.equal(h.calls.processes.length, 0);
});

test('concurrent dispatches of one spawn share the in-flight routing promise', async () => {
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const h = host({ process: async () => pending }); await h.command('on subagent');
  const a = spawn(h, child()), b = spawn(h, child());
  await new Promise(done => setImmediate(done));
  assert.equal(h.calls.processes.length, 1);
  resolve({ exitCode: 0, stdout: JSON.stringify({ status: 'recommended', decisions: {
    subagent: { choice: 'subagent-10', model: 'haiku', effort: 'low', confidence: 0.9 } } }), stderr: '' });
  assert.equal((await a).model, 'haiku'); assert.equal((await b).model, 'haiku');
});

test('separate spawn identities route separately even with identical prompts', async () => {
  const h = host(); await h.command('on subagent');
  await spawn(h, child('one')); await spawn(h, child('two'));
  await spawn(h, child('one', { parentAgentId: 'another-parent' }));
  assert.equal(h.calls.processes.length, 3);
});

test('continuing an existing child has no new spawn routing event', async () => {
  const h = host(); await h.command('on subagent'); await spawn(h);
  const followup = { tool: 'SendMessage', tool_use_id: 'followup',
    input: { to: 'child-id', message: 'Continue inspecting' } };
  assert.equal(await h.event('tool.call', followup), followup);
  assert.equal(h.calls.processes.length, 1);
});

test('native resume events keep the existing pair and never ask Jev again', async () => {
  const h = host(); await h.command('on subagent'); await spawn(h);
  const e = child('resume-event', { resume: { agentId: 'child-id' }, model: 'haiku', effort: 'low' });
  assert.equal(await spawn(h, e), e);
  assert.equal(h.calls.processes.length, 1); assert.equal(h.calls.configs, 1);
  assert.ok(h.calls.logs.some(text => text.includes('resumed agent keeps its existing model and effort')));
});

test('workflow agents with a shared tool ID use host dispatch without merging their independent work', async () => {
  const h = host(); await h.command('on subagent');
  for (const agentIndex of [1, 2]) {
    const e = child('shared-workflow-call', { workflow: { runId: 'wf_test', agentIndex } });
    assert.equal(await spawn(h, e, 'sonnet'), e);
  }
  assert.equal(h.calls.processes.length, 0); assert.equal(h.calls.configs, 0);
  assert.ok(h.calls.logs.some(text => text.includes('no safe independent unit/cache identification yet')));
  assert.ok(!h.calls.logs.some(text => text.includes('immutable')));
  assert.equal((await spawn(h, child('shared-workflow-call'))).model, 'haiku');
  assert.equal(h.calls.processes.length, 1);
});

test('failed routing is cached and keeps inheritance on repeated dispatch of the same spawn', async () => {
  const h = host({ process: async () => { throw new Error('private secret /private/path'); } });
  await h.command('on subagent'); const e = child();
  assert.equal(await spawn(h, e, 'sonnet'), e);
  assert.equal(await spawn(h, { ...e }, 'sonnet').then(value => value.model), undefined);
  assert.equal(h.calls.processes.length, 1);
  assert.equal(h.calls.logs.filter(text => text.includes('routing failed')).length, 1);
  assert.ok(!JSON.stringify(h.calls.logs).includes('private secret'));
  assert.ok(!JSON.stringify(h.calls.logs).includes('/private/path'));
});

test('missing-key fallback is remembered even if the key becomes available later', async () => {
  const h = host(); await h.command('on subagent'); h.key('');
  await spawn(h, child(), 'sonnet'); h.key('new-synthetic-key');
  await spawn(h, child(), 'sonnet'); assert.equal(h.calls.processes.length, 0);
  await spawn(h, child('new-child')); assert.equal(h.calls.processes.length, 1);
});

test('invalid recommendations fail once without leaking output or dispatching another spawn', async () => {
  for (const process of [
    async () => ({ exitCode: 1, stdout: 'secret-output', stderr: 'private-error' }),
    async () => ({ exitCode: 0, stdout: 'invalid JSON', stderr: '' }),
    async () => ({ exitCode: 0, stdout: JSON.stringify({ status: 'recommended', decisions: {
      subagent: { choice: 'private/model', confidence: 1 } } }), stderr: '' }),
  ]) {
    const h = host({ process }); await h.command('on subagent');
    await spawn(h, child(), 'sonnet'); await spawn(h, child(), 'sonnet');
    assert.equal(h.calls.processes.length, 1);
    assert.ok(!JSON.stringify(h.calls.logs).includes('secret-output'));
    assert.ok(!JSON.stringify(h.calls.logs).includes('private-error'));
  }
});

test('downstream spawn errors propagate once and retain the already consumed route', async () => {
  const h = host(); await h.command('on subagent'); let count = 0;
  const error = new Error('host rejected spawn');
  await assert.rejects(h.event('agent.spawn', child(), async () => { count++; throw error; }), error);
  assert.equal(count, 1); assert.equal(h.calls.processes.length, 1);
  assert.equal((await spawn(h)).model, 'haiku'); assert.equal(h.calls.processes.length, 1);
});

test('explicit child models and forks preserve host inputs without a Jev request', async () => {
  const h = host(); await h.command('on subagent');
  for (const e of [child('explicit', { model: 'opus' }), child('fork', { fork: true })]) {
    assert.equal(await spawn(h, e, 'opus'), e);
  }
  assert.equal(h.calls.processes.length, 0);
  assert.ok(h.calls.logs.some(text => text.includes('fork inherits')));
});

test('missing stable IDs report the limitation and route each event once without merging by prompt', async () => {
  const h = host(); await h.command('on subagent');
  const e = child(undefined, { tool_use_id: undefined });
  await spawn(h, e); await spawn(h, e);
  assert.equal(h.calls.processes.length, 2);
  assert.ok(h.calls.logs.some(text => text.includes('no stable spawn ID')));
});

test('disabling routing skips cached choices and reenabling does not retry consumed routing', async () => {
  const h = host(); await h.command('on subagent'); await spawn(h);
  await h.command('off'); const e = child();
  assert.equal(await spawn(h, e, 'sonnet'), e);
  await h.command('on subagent'); assert.equal((await spawn(h, e)).model, 'haiku');
  assert.equal(h.calls.processes.length, 1);
});

test('session state is isolated and end clears flags and cached routing', async () => {
  const a = host(), b = host(); await a.command('on subagent'); await spawn(a);
  assert.match((await b.command('status')).text, allOff);
  await a.event('session.end', {});
  assert.match((await a.command('status')).text, allOff);
  await a.command('on subagent'); await spawn(a);
  assert.equal(a.calls.processes.length, 2);
});

test('live inventory filters virtual modes, context suffixes, duplicates and private IDs', () => {
  const candidates = modelCandidates([{ key: 'model', kind: 'choice', isLocked: false,
    options: ['default', 'sonnet', 'opus', 'haiku', 'fable', 'best', 'opusplan', 'sonnet[1m]',
      'claude-opus-test', 'arn:aws:private', '/private/model', 'custom/name', 'sonnet'] }]);
  assert.deepEqual(models(candidates), ['sonnet', 'opus', 'haiku', 'fable', 'claude-opus-test']);
  assert.deepEqual(modelCandidates([{ key: 'model', kind: 'choice', isLocked: true, options: ['sonnet'] }]), []);
  assert.deepEqual(modelCandidates([{ key: 'model', kind: 'text', options: ['sonnet'] }]), []);
});

test('locked, absent or restricted inventory falls back without API and is not retried for that spawn', async () => {
  for (const options of [{ rows: [] }, { settings: { availableModels: [] } },
    { rows: [{ key: 'model', kind: 'choice', isLocked: true, options: ['haiku'] }] }]) {
    const h = host(options); await h.command('on subagent');
    await spawn(h, child(), 'sonnet'); await spawn(h, child(), 'sonnet');
    assert.equal(h.calls.processes.length, 0); assert.equal(h.calls.configs, 1);
    assert.ok(h.calls.logs.some(text => /unavailable|locked/.test(text)));
  }
  const h = host({ settings: { availableModels: ['haiku'] } }); await h.command('on subagent'); await spawn(h);
  assert.deepEqual(models(JSON.parse(h.calls.processes[0].init.stdin).decisions.subagent), ['haiku']);
});

test('each independent spawn reads fresh candidates without rerouting earlier units', async () => {
  const h = host(); await h.command('on subagent'); await spawn(h, child('one'));
  h.rows([{ key: 'model', kind: 'choice', isLocked: false, options: ['haiku'] }]);
  await spawn(h, child('two')); await spawn(h, child('one'));
  assert.equal(h.calls.configs, 2);
  assert.deepEqual(models(JSON.parse(h.calls.processes[1].init.stdin).decisions.subagent), ['haiku']);
});

test('feature summaries contain no source text, code, secret values or private paths', () => {
  const source = 'Review a complex concurrent payment upload with images /private/project/file.js '
    + 'test-env-secret function privateAlgorithm() { return "secret"; }';
  const summary = summarizeTask(source);
  assert.match(summary, /review/); assert.match(summary, /concurrency/); assert.match(summary, /payments/);
  for (const value of ['test-env-secret', '/private/project', 'privateAlgorithm', 'file.js', source]) {
    assert.ok(!summary.includes(value));
  }
});

test('manual exclude/include is human-only, atomic, key-free and never enables routing', async () => {
  const h = host({ key: '' });
  assert.match((await h.command('exclude claude-fable-5-1')).text, /unavailable=fable/);
  assert.match((await h.command('status')).text, allOff);
  assert.equal(h.calls.env, 0); assert.equal(h.calls.processes.length, 0);
  for (const origin of ['plugin', 'peer', 'unclassified']) {
    assert.match((await h.command('include fable', origin)).text, /user command/);
    assert.match((await h.command('exclude opus', origin)).text, /user command/);
  }
  assert.match((await h.command('exclude opus /private/id')).text, /Usage/);
  assert.match((await h.command('status')).text, /unavailable=fable/);
  assert.match((await h.command('include Fable')).text, /unavailable=none/);
  assert.match((await h.command('include fable')).text, /does not verify restored quota/);
  assert.equal(h.calls.env, 0);
});

test('family exclusions filter aliases and full IDs while unknown quotas stay eligible', () => {
  const rows = [{ key: 'model', kind: 'choice', isLocked: false,
    options: ['fable', 'claude-fable-5-1', 'sonnet', 'claude-3-5-sonnet-20241022', 'haiku', 'opus'] }];
  assert.equal(models(modelCandidates(rows)).length, 6);
  assert.deepEqual(models(modelCandidates(rows, undefined, new Set(['claude-fable-5-1']))),
    ['sonnet', 'claude-3-5-sonnet-20241022', 'haiku', 'opus']);
  assert.deepEqual(models(modelCandidates(rows, undefined, ['sonnet', 'fable'])), ['haiku', 'opus']);
});

test('known exclusions guard fresh and cached native/combined choices without new routing or dispatch', async () => {
  const rows = [{ key: 'model', kind: 'choice', isLocked: false, options: ['fable', 'haiku'] }];
  const h = host({ rows, choice: 'fable' }); await h.command('on subagent');
  await spawn(h, child('cached-native'), 'claude-fable-5-1');
  await h.command('on skill');
  await spawn(h, child('cached-combined', { model: 'fable' }), 'claude-fable-5-1');
  await h.command('exclude fable');
  let count = 0;
  for (const e of [child('cached-combined'), child('fresh', { model: 'claude-fable-5-1' })]) {
    const result = await h.event('agent.spawn', e, async () => { count++; });
    assert.match(result.deny, /fable.*unavailable/);
  }
  await h.command('off skill');
  const result = await h.event('agent.spawn', child('cached-native'), async () => { count++; });
  assert.match(result.deny, /fable.*unavailable/);
  assert.equal(count, 0); assert.equal(h.calls.processes.length, 1);
});

test('future native decisions omit manually excluded families and keep other model options', async () => {
  const h = host({ rows: [{ key: 'model', kind: 'choice', isLocked: false, options: ['fable', 'haiku'] }] });
  await h.command('on subagent'); await h.command('exclude fable');
  assert.equal((await spawn(h)).model, 'haiku');
  const request = JSON.parse(h.calls.processes[0].init.stdin);
  assert.deepEqual(models(request.decisions.subagent), ['haiku']);
  assert.deepEqual(request.decisions.subagent.map(item => item.effort), EFFORTS);
});

test('host quota failures pass through once without automatic exclusions or replay', async () => {
  for (const throws of [false, true]) {
    const h = host({ rows: [{ key: 'model', kind: 'choice', isLocked: false, options: ['fable', 'haiku'] }],
      choice: 'fable' });
    await h.command('on subagent'); let count = 0;
    const error = new Error('Fable is out of credits');
    const denial = { deny: error.message };
    const operation = h.event('agent.spawn', child('failed'), async e => {
      assert.equal(e.model, 'fable'); count++; if (throws) throw error; return denial;
    });
    if (throws) await assert.rejects(operation, value => value === error);
    else assert.equal(await operation, denial);
    assert.equal(count, 1); assert.equal(h.calls.processes.length, 1);
    assert.match((await h.command('status')).text, /unavailable=none/);
    assert.equal((await spawn(h, child('next-planned'), 'claude-fable-test')).model, 'fable');
    assert.equal(h.calls.processes.length, 2);
    assert.ok(JSON.parse(h.calls.processes[1].init.stdin).decisions.subagent.some(item => item.model === 'fable'));
  }
});

test('off pauses dispatch guards but retains manual exclusions until this session ends', async () => {
  const h = host(); await h.command('on all'); await h.command('exclude fable'); await h.command('off');
  const e = child('off-allowed', { model: 'fable' }); assert.equal(await spawn(h, e, 'fable'), e);
  assert.match((await h.command('status')).text, /unavailable=fable/);
  await h.command('on skill');
  assert.equal(await spawn(h, e, 'fable'), e);
  await h.command('on subagent'); let count = 0;
  assert.ok((await h.event('agent.spawn', e, async () => { count++; })).deny);
  assert.equal(count, 0);
  const other = host(); assert.match((await other.command('status')).text, /unavailable=none/);
  await h.event('session.end', {}); assert.match((await h.command('status')).text, /unavailable=none/);
});
