// Claude Code mods: every session owns its routing state inside register().
const SCOPES = ['skill', 'subagent'];
const USAGE = 'Usage: /jev [status | on/off [skill subagent | all] | exclude/include <model...>]';
const USER_ORIGINS = ['composer', 'bridge', 'sdk'];
const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'];
// A child's first model request can precede its spawn's answer; wait this long for the agentId.
const PENDING_WAIT_MS = 3000;
// Flags and exclusions live in the plugin store: the last explicit command holds across sessions.
const STORE_KEY = 'routing';
const BRIEF_PREFIX = 'Jev routing: ';

export function parseControl(args) {
  const words = args.trim().split(/\s+/).filter(Boolean);
  const action = words.shift() ?? 'status';
  if (action === 'status') return words.length ? null : { action, scopes: [] };
  if (action === 'exclude' || action === 'include') {
    const models = words.map(word => word.toLowerCase());
    return models.length && models.every(publicModel) ? { action, models } : null;
  }
  if (action !== 'on' && action !== 'off') return null;
  if (!words.length) return { action, scopes: [...SCOPES] };
  if (words.length === 1 && words[0] === 'all') return { action, scopes: [...SCOPES] };
  if (!words.every(word => SCOPES.includes(word))) return null;
  return { action, scopes: [...new Set(words)] };
}

function publicModel(id) {
  return typeof id === 'string' && (/^(sonnet|opus|haiku|fable)$/.test(id)
    || /^claude-[a-z0-9][a-z0-9.-]{0,120}$/.test(id));
}

function exclusionKey(model) {
  if (!publicModel(model)) return undefined;
  const family = model.match(/^(?:claude-(?:[0-9]+(?:-[0-9]+)*-)?)?(sonnet|opus|haiku|fable)(?:-|$)/);
  return family ? family[1] : model;
}

function excluded(model, unavailable) {
  return unavailable.has(exclusionKey(model));
}

// Drops unknown scopes and non-canonical exclusions from a stored record.
function storedRouting(value) {
  const list = (items, valid) => Array.isArray(items) ? [...new Set(items.filter(valid))] : [];
  return { enabled: list(value?.enabled, item => SCOPES.includes(item)),
    unavailable: list(value?.unavailable, item => exclusionKey(item) === item).sort() };
}

function spawnKey(parentId, toolId) {
  return typeof toolId === 'string' && toolId ? JSON.stringify([parentId ?? null, toolId]) : undefined;
}

export function modelCandidates(rows, availableModels, excludedModels = new Set(), efforts = EFFORTS) {
  const row = Array.isArray(rows) && rows.find(item => item.key === 'model');
  if (!row || row.kind !== 'choice' || row.isLocked || !Array.isArray(row.options)) return [];
  if (availableModels !== undefined && !Array.isArray(availableModels)) return [];
  return [...new Set(row.options)].filter(id => publicModel(id)
    && (availableModels === undefined || availableModels.includes(id))
    && ![...excludedModels].some(model => exclusionKey(model) === exclusionKey(id)))
    .flatMap(model => efforts.map(effort => ({ model, effort })))
    .map(({ model, effort }, index) => ({ id: `subagent-${index}`, model, effort,
      description: effort === null
        ? `Current host model option: ${model}; effort is host-controlled.`
        : `Current host model option: ${model} at ${effort} effort; the host lowers or drops an effort this model does not support.` }));
}

export function summarizeTask(text) {
  // Output only fixed feature names: no prompt substrings cross the process boundary.
  const source = typeof text === 'string' ? text : '';
  const categories = [
    ['review', /\breview\b|審查|檢視|review/i],
    ['debug', /\b(debug|diagnos\w*|bug|failure|broken|fix)\b|除錯|診斷|修正|錯誤/i],
    ['implement', /\b(implement|build|add|create|refactor)\b|實作|新增|建立|重構/i],
    ['docs', /\b(doc\w*|write|prose|readme)\b|文檔|文件|撰寫/i],
    ['testing', /\b(test\w*|regression|verify|validation)\b|測試|驗證/i],
    ['research', /\b(research|investigate|compare|explain)\b|研究|調查|比較|解釋/i],
  ].filter(([, pattern]) => pattern.test(source)).map(([name]) => name);
  const markers = [
    ['images', /\b(image|screenshot|visual|photo)\w*\b|圖片|截圖|視覺/i],
    ['audio', /\b(audio|speech|voice)\b|音訊|語音/i],
    ['security', /\b(security|auth\w*|secret\w*|upload\w*|permission\w*)\b|安全|驗證|上傳|權限/i],
    ['payments', /\b(payment\w*|billing|financial)\b|付款|帳務|金融/i],
    ['database', /\b(database|schema|migration|sql)\b|資料庫|遷移/i],
    ['concurrency', /\b(concurren\w*|parallel|race|thread\w*)\b|並行|競態|執行緒/i],
  ].filter(([, pattern]) => pattern.test(source)).map(([name]) => name);
  return JSON.stringify({ categories: categories.length ? categories : ['general'],
    size: source.length < 200 ? 'short' : source.length < 2000 ? 'medium' : 'long',
    complexity: /\b(complex|architecture|multi\w*|distributed)\b|複雜|架構|跨專案/i.test(source)
      ? 'high' : 'unspecified', markers });
}

function safeLog($, text) {
  try { $.ui.log(text); } catch { /* Logging never changes dispatch. */ }
}

function reportedModel(model) {
  return publicModel(model) ? model : '[host model omitted]';
}

async function chooseSubagent($, text, unavailable, stableId) {
  try {
    const rows = await $.config.list();
    const settings = await $.settings.read();
    let note;
    if (await $.env.get('CLAUDE_CODE_EFFORT_LEVEL')) note = 'locked by CLAUDE_CODE_EFFORT_LEVEL';
    else if (!stableId) note = 'host-controlled (no stable spawn ID to detect an explicit Agent effort)';
    if (note) safeLog($, `Jev subagent: effort ${note}; routing the model only.`);
    const efforts = note ? [null] : EFFORTS;
    const models = modelCandidates(rows, settings.availableModels, unavailable, efforts);
    if (!models.length) {
      safeLog($, 'Jev subagent: model inventory unavailable or locked; using inheritance.');
      return undefined;
    }
    if (!await $.env.get('JEV_API_KEY')) {
      safeLog($, 'Jev subagent: missing JEV_API_KEY; using inheritance.');
      return undefined;
    }
    const result = await $.process.run(['python3', `${$.plugin.root}/skills/jev/scripts/route.py`], {
      stdin: JSON.stringify({ host: 'Claude Code native mod', task: summarizeTask(text),
        decisions: { subagent: models } }),
      timeoutMs: 17000,
    });
    if (result.exitCode !== 0) throw new Error('routing failed');
    const answer = JSON.parse(result.stdout);
    const decision = answer?.decisions?.subagent;
    const selected = decision && models.find(item => item.id === decision.choice);
    if (answer.status !== 'recommended' || !decision
      || !selected || decision.model !== selected.model || decision.effort !== selected.effort
      || typeof decision.confidence !== 'number' || !Number.isFinite(decision.confidence)
      || decision.confidence < 0 || decision.confidence > 1) throw new Error('invalid routing result');
    return { model: selected.model, effort: selected.effort, note };
  } catch {
    safeLog($, 'Jev subagent: routing failed; using inheritance.');
    return undefined;
  }
}

function receiptHelper(root) {
  return `${root}/skills/jev/scripts/claude_route.py`;
}

function shellQuote(text) {
  return `'${text.replaceAll("'", "'\\''")}'`;
}

function beginHint(root) {
  return `Before this spawn run python3 ${shellQuote(receiptHelper(root))} begin (see its --help), then put its `
    + 'brief_line verbatim in the Agent prompt and its model and effort in Agent.model and Agent.effort.';
}

function receiptDenial(code, id, expected) {
  const copy = typeof expected?.brief_line === 'string' ? ` Expected line: ${expected.brief_line}` : '';
  switch (code) {
    case 'receipt_missing': return `no routing receipt ${id} in this session.`;
    case 'receipt_expired': return `routing receipt ${id} expired.`;
    case 'receipt_used': return `routing receipt ${id} was already used by another spawn.`;
    case 'brief_mismatch': return `the brief line differs from routing receipt ${id}.${copy}`;
    case 'receipt_mismatch': return `Agent.model/Agent.effort differ from routing receipt ${id}: expected `
      + `model=${expected?.model ?? 'unset'} effort=${expected?.effort ?? 'null'}.${copy}`;
    default: return undefined;
  }
}

// Combined routing is agent-prepared; the receipt proves claude_route.py begin ran for this spawn.
async function claimReceipt($, e, key, effort) {
  const lines = (typeof e.prompt === 'string' ? e.prompt : '').split('\n')
    .map(line => line.trim()).filter(line => line.startsWith(BRIEF_PREFIX));
  const refuse = reason => ({ deny: `Jev: combined routing ${reason} ${beginHint($.plugin.root)}` });
  if (lines.length !== 1) {
    return refuse(lines.length ? `found ${lines.length} "${BRIEF_PREFIX}" lines in this Agent prompt; keep exactly one.`
      : `found no "${BRIEF_PREFIX}" line in this Agent prompt.`);
  }
  let id;
  try { id = JSON.parse(lines[0].slice(BRIEF_PREFIX.length)).receipt; } catch { /* Refused below. */ }
  if (typeof id !== 'string') return refuse(`found an unreadable "${BRIEF_PREFIX}" line.`);
  let answer;
  try {
    const result = await $.process.run(['python3', receiptHelper($.plugin.root), 'claim'], {
      stdin: JSON.stringify({ session_id: await $.session.id(), receipt_id: id, spawn: key ?? null,
        model: e.model ?? null, effort: effort ?? null, brief_line: lines[0] }),
      timeoutMs: 5000,
    });
    answer = JSON.parse(result.stdout);
  } catch { /* Refused below. */ }
  if (answer?.status === 'ok' && answer.receipt && typeof answer.receipt === 'object') return { id, receipt: answer.receipt };
  const denial = receiptDenial(answer?.code, id, answer?.expected);
  if (denial) return refuse(denial);
  return { deny: 'Jev: combined routing receipt check failed; dispatch blocked. Retry the spawn, '
    + 'or ask the user to run /jev off skill to leave combined routing.' };
}

async function childEffort($, agentId, childEfforts, pendingSpawns) {
  if (agentId === undefined) return undefined;
  if (!childEfforts.has(agentId) && pendingSpawns.size) {
    try {
      await Promise.race([Promise.allSettled([...pendingSpawns]), $.clock.sleep(PENDING_WAIT_MS)]);
    } catch { /* An unknown child keeps its host effort. */ }
  }
  return childEfforts.get(agentId);
}

// Restores the saved routing into this session; saved scopes stay off without JEV_API_KEY.
async function restoreRouting($, enabled, unavailable, blocked) {
  let saved;
  try { saved = storedRouting(await $.store.get(STORE_KEY)); } catch {
    safeLog($, 'Jev: saved routing state is unreadable; flags start off and exclusions start empty.');
    return;
  }
  for (const model of saved.unavailable) unavailable.add(model);
  if (!saved.enabled.length) return;
  let keyPresent = false;
  try { keyPresent = !!await $.env.get('JEV_API_KEY'); } catch { /* Saved scopes stay off. */ }
  for (const scope of saved.enabled) (keyPresent ? enabled : blocked).add(scope);
  if (!keyPresent) safeLog($, `Jev: JEV_API_KEY is missing; saved ${saved.enabled.join(',')} stays off.`);
}

// Merges one field into the stored record so a command keeps what other sessions saved in the other field.
async function saveRouting($, field, apply) {
  try {
    const saved = storedRouting(await $.store.get(STORE_KEY));
    const next = storedRouting({ ...saved, [field]: apply(saved[field]) });
    await $.store.set(STORE_KEY, next);
    return next;
  } catch {
    safeLog($, 'Jev: routing state could not be saved; the change applies to this session only.');
    return undefined;
  }
}

export function register(on) {
  const enabled = new Set();
  const spawns = new Map();
  const unavailable = new Set();
  // Agent tool arguments by spawn key: agent.spawn does not carry the call's effort.
  const agentCalls = new Map();
  // Jev-selected effort by child agentId, applied to each of that child's model requests.
  const childEfforts = new Map();
  const pendingSpawns = new Set();
  // Saved scopes left off at start because JEV_API_KEY was missing.
  const blocked = new Set();
  let lastEvidence, sessionId, root;
  let serveBareCommand = false;

  function reset() {
    enabled.clear(); spawns.clear(); unavailable.clear(); agentCalls.clear(); childEfforts.clear();
    pendingSpawns.clear(); blocked.clear(); lastEvidence = undefined; serveBareCommand = false;
    sessionId = undefined; root = undefined;
  }

  function flags() {
    return SCOPES.map(scope => `${scope}=${enabled.has(scope) ? 'on' : 'off'}`).join(' ');
  }

  function context() {
    return `JEV_NATIVE_ROUTING ${flags()}. The main conversation uses the host model setting. `
      + `Manually excluded models: ${[...unavailable].sort().join(', ') || 'none'}. `
      + 'Flags and exclusions persist across sessions until an explicit user command changes them. '
      + 'Exclude every model/effort option in those families from each prepared batch and recheck cached '
      + 'choices before dispatch. Quota for other models is unknown, so keep them eligible. '
      + 'Only explicit human exclude/include commands change this list; host errors never change it automatically. '
      + 'Keep the original skills and brief; blocked dispatch does not authorize a replacement model or duplicate work. '
      + 'When skill=on, continue the user-enabled Jev workflow for zero or more optional skills once per '
      + 'independent work unit, reusing its result, including failures, through the batch and continuations. '
      + 'When skill=on and subagent=on, prepare one combined Jev batch per child unit for its applicable '
      + 'skill and subagent decisions, put the validated model in Agent.model, a supported non-null effort '
      + 'in Agent.effort, and selected skills in the brief. Verify per-model effort choices against the actual '
      + 'Agent tool. If its per-model effort combinations cannot be verified, report effort-routing unavailable '
      + 'and keep model and skill decisions in that same batch using default-effort candidates. '
      + 'effort:null means omit Agent.effort and use host-controlled effort. Applying a verified Jev-selected '
      + 'concrete effort is this skill\'s explicit per-invocation instruction, rather than an agent choosing effort on its own. '
      + 'If the user fixed effort and compatible models cannot be verified, preserve the original model and '
      + 'that effort, route only optional skills, and never replace the user\'s value with null. '
      + 'Reuse a failed batch as inheritance and ordinary skills; the native hook never reroutes this combined path. '
      + combinedReceipts()
      + 'When skill=off and subagent=on, native hooks choose the child model and effort; omit Agent.model and Agent.effort unless the user fixed them. '
      + 'Native candidates pair each offered model with low, medium, high, xhigh and max; the mod applies the chosen '
      + 'effort to each of that child\'s model requests. The host silently lowers or drops an effort the model does '
      + 'not support, so native status reports the requested effort and an unverified actual one. An explicit '
      + 'Agent.effort, a spawn without a stable ID, or CLAUDE_CODE_EFFORT_LEVEL keeps effort host-controlled. '
      + 'Resumed agents keep their existing pair. Workflow routing remains host-owned because this path '
      + 'does not yet have safe independent unit/cache identification. '
      + 'Read installed Jev instructions as needed under the existing human authorization. Native /jev controls '
      + 'require an explicit user command; this context does not authorize changing the flags. '
      + 'Explicit user choices and mandatory skill rules still apply.';
  }

  function combinedReceipts() {
    if (!enabled.has('skill') || !enabled.has('subagent') || !root) return '';
    const session = sessionId === undefined ? '' : `"session_id":${JSON.stringify(sessionId)},`;
    return 'The mod enforces combined routing with receipts: before each new non-fork Agent spawn, run '
      + `python3 ${shellQuote(receiptHelper(root))} begin with JSON stdin {${session}"original":{"model":<planned `
      + 'model or null>,"effort":<planned effort or null>},"request":<one route.py batch with skill and subagent '
      + 'decisions>}; read its --help for skip_subagent and fields. Put its brief_line verbatim as one line of the '
      + 'Agent prompt, set Agent.model to its model and Agent.effort to its effort, omitting each when null, and have '
      + 'the child load its skills. A failed route still returns a fallback receipt that keeps the original settings; '
      + 'report it. The mod denies a spawn without exactly one such line, with an unknown, expired or used receipt, '
      + 'or with a different model, effort or line; each receipt serves one spawn for 30 minutes. Give a child that '
      + 'may delegate this command and session ID. ';
  }

  function status() {
    return `Jev: ${flags()}`
      + `; unavailable=${[...unavailable].sort().join(',') || 'none'}`
      + (blocked.size ? `; saved ${[...blocked].join(',')} off until JEV_API_KEY is set` : '')
      + (lastEvidence ? `; last ${lastEvidence}` : '');
  }

  on('session.start', async ($, e, next) => {
    reset();
    root = $.plugin.root;
    try { sessionId = await $.session.id(); } catch { /* The helper falls back to CLAUDE_CODE_SESSION_ID. */ }
    await restoreRouting($, enabled, unavailable, blocked);
    const existing = (await $.command.list()).find(command => command.name === 'jev');
    if (!existing) {
      await $.command.register({ name: 'jev', description: 'Configure Jev routing; settings persist across sessions',
        argumentHint: '[status | on/off [skill subagent | all] | exclude/include <model...>]' });
      serveBareCommand = true;
    } else if ((existing.source === 'plugin' && existing.plugin === 'shuaigle')
      || (existing.source === 'user'
        && (existing.description.startsWith('Jev routing for optional skills and subagent model/effort pairs.')
          || existing.description.startsWith('Jev routing for optional skills and subagent models.')
          || existing.description.startsWith('Jev routing for task models, skills, and subagent models.')))) {
      serveBareCommand = true;
    } else safeLog($, 'Jev: existing /jev command preserved; use /shuaigle:jev for routing controls.');
    return next(e);
  });

  on('command.run', { command: ['jev', 'shuaigle:jev'] }, async ($, e, next) => {
    if (e.command === 'jev' && !serveBareCommand) return next(e);
    if (!USER_ORIGINS.includes(e.origin?.kind)) {
      return { text: 'Jev controls require an explicit user command.' };
    }
    const control = parseControl(e.args);
    if (!control) return { text: USAGE, context: [context()] };
    if (control.action === 'exclude' || control.action === 'include') {
      const keys = control.models.map(exclusionKey);
      const change = list => control.action === 'exclude' ? [...list, ...keys] : list.filter(key => !keys.includes(key));
      const saved = await saveRouting($, 'unavailable', change);
      const models = saved ? saved.unavailable : change([...unavailable]);
      unavailable.clear();
      for (const model of models) unavailable.add(model);
      return { text: `${status()}${saved ? '' : '; not saved'}; known aliases and full IDs in a family share its exclusion; inclusion does not verify restored quota.`,
        context: [context()] };
    }
    if (control.action === 'status') return { text: status(), context: [context()] };
    if (control.action === 'on') {
      let keyPresent = false;
      try { keyPresent = !!await $.env.get('JEV_API_KEY'); } catch { /* Keep flags unchanged. */ }
      if (!keyPresent) return { text: `JEV_API_KEY is missing; ${status()}`, context: [context()] };
      for (const scope of control.scopes) enabled.add(scope);
    } else {
      for (const scope of control.scopes) enabled.delete(scope);
    }
    blocked.clear();
    const saved = await saveRouting($, 'enabled', () => [...enabled]);
    return { text: `${status()}${saved ? '' : '; not saved'}`, context: [context()] };
  });

  on('prompt.submit', ($, e, next) => next({ ...e, context: [...(e.context ?? []), context()] }));

  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const key = spawnKey(e.agentId, e.tool_use_id);
    if (!key) return next(e);
    agentCalls.set(key, { effort: e.effort });
    try { return await next(e); } finally { agentCalls.delete(key); }
  });

  on('agent.spawn', async ($, e, next) => {
    if (!enabled.has('subagent')) return next(e);
    if (e.resume) {
      safeLog($, 'Jev subagent: resumed agent keeps its existing model and effort.');
      return next(e);
    }
    if (e.workflow) {
      safeLog($, 'Jev subagent: workflow path has no safe independent unit/cache identification yet; using host dispatch.');
      return next(e);
    }
    if (e.fork) {
      safeLog($, 'Jev subagent: fork inherits its parent model.');
      return next(e);
    }
    // tool_use_id is the host's pinned spawn identity, scoped to its parent loop.
    const key = spawnKey(e.parentAgentId, e.tool_use_id);
    const explicitEffort = key ? agentCalls.get(key)?.effort : undefined;
    if (excluded(e.model, unavailable)) return { deny: `Jev: ${exclusionKey(e.model)} is manually excluded and unavailable; dispatch blocked.` };
    let state = key && spawns.get(key);
    let choice;
    // A spawn already routed natively before skill was enabled keeps that decision.
    if (enabled.has('skill') && (!state || state.claim)) {
      if (!state) {
        state = { claim: claimReceipt($, e, key, explicitEffort), reported: false };
        if (key) spawns.set(key, state);
      }
      const claimed = await state.claim;
      if (claimed.deny) {
        // A refused claim consumed nothing; a later event of this spawn may claim again.
        if (key && spawns.get(key) === state) spawns.delete(key);
        return { deny: claimed.deny };
      }
      const { receipt } = claimed;
      if (excluded(e.model ?? receipt.model, unavailable)) {
        return { deny: `Jev: ${exclusionKey(e.model ?? receipt.model)} is manually excluded and unavailable; cached dispatch blocked.` };
      }
      // A repeated event of a claimed spawn must still carry the receipt's model.
      if ((e.model ?? null) !== receipt.model) {
        return { deny: `Jev: Agent.model differs from routing receipt ${claimed.id}: expected model=${receipt.model ?? 'unset'}.` };
      }
      const routing = receipt.status === 'fallback' ? `fallback(${receipt.code})` : 'recommended';
      if (receipt.status === 'fallback' && !state.failureReported) {
        state.failureReported = true;
        safeLog($, `Jev subagent: routing failed (${receipt.code}); receipt ${claimed.id} keeps the original spawn settings.`);
      }
      const result = await next(e);
      if (result?.model && !state.reported) {
        state.reported = true;
        lastEvidence = `subagent receipt=${claimed.id} requested=${receipt.model ?? 'inherited'} `
          + `actual=${reportedModel(result.model)} effort requested=${receipt.effort ?? 'host-controlled'} `
          + `skills=${Array.isArray(receipt.skills) && receipt.skills.length ? receipt.skills.join(',') : 'none'} routing=${routing}`;
        safeLog($, `Jev ${lastEvidence}`);
      }
      return result;
    } else if (state?.claim) {
      // A receipt-claimed spawn repeated after skill was disabled keeps its receipt's pair.
      const { receipt } = await state.claim;
      choice = receipt && { model: receipt.model, effort: receipt.effort };
    } else if (e.model !== undefined) {
      choice = { model: e.model, effort: explicitEffort ?? null };
    } else if (explicitEffort !== undefined) {
      if (!state) {
        state = { choice: Promise.resolve(undefined), reported: false };
        if (key) spawns.set(key, state);
      }
      if (!state.constraintReported) {
        state.constraintReported = true;
        safeLog($, 'Jev subagent: explicit effort has no verified compatible model inventory; preserving host dispatch.');
      }
    } else {
      if (!state) {
        state = { choice: chooseSubagent($, e.prompt, unavailable, !!key), reported: false };
        if (key) spawns.set(key, state);
        else safeLog($, 'Jev subagent: no stable spawn ID; routing applies to this event only.');
      }
      choice = await state.choice;
    }
    const model = choice?.model ?? e.model;
    if (excluded(model, unavailable)) return { deny: `Jev: ${exclusionKey(model)} is manually excluded and unavailable; cached dispatch blocked.` };
    const routed = choice && e.model === undefined;
    const effort = routed ? choice.effort : null;
    // Hold the child's early model requests until its agentId maps to the selected effort.
    let release, gate;
    if (effort) { gate = new Promise(done => { release = done; }); pendingSpawns.add(gate); }
    let result;
    try {
      // There is one existing spawn, not a second agent created by this hook.
      result = await next(routed ? { ...e, model: choice.model } : e);
      if (effort && result?.agentId) {
        childEfforts.set(result.agentId, { effort, model: choice.model, reported: false });
      }
    } finally {
      if (gate) { pendingSpawns.delete(gate); release(); }
    }
    if (choice && result?.model && state && !state.reported) {
      state.reported = true;
      const effortText = effort ? `requested=${effort} actual=awaiting first request`
        : choice.note ?? 'host-controlled';
      lastEvidence = `subagent requested=${choice.model} actual=${reportedModel(result.model)} effort ${effortText}`;
      safeLog($, `Jev ${lastEvidence}`);
    }
    return result;
  });

  on('turn.step', async function* ($, e, next) {
    const state = await childEffort($, e.agentId, childEfforts, pendingSpawns);
    if (!state) return yield* next(e);
    // The host sends no effort to a model without one and lowers an unsupported level silently.
    const actual = e.effort === undefined ? 'none (the model takes no effort)'
      : 'unverified (the host lowers an unsupported effort without reporting it)';
    if (!state.reported) {
      state.reported = true;
      lastEvidence = `subagent requested=${state.model} effort requested=${state.effort} actual=${actual}`;
      safeLog($, `Jev ${lastEvidence}`);
    }
    if (e.effort === undefined || e.effort === state.effort) return yield* next(e);
    return yield* next({ ...e, effort: state.effort });
  });

  on('session.end', ($, e, next) => { reset(); return next(e); });
}
