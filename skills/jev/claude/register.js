// Claude Code mods: every session owns its routing state inside register().
const SCOPES = ['task', 'skill', 'subagent'];
const USAGE = 'Usage: /jev [status | on [task skill subagent | all] | off [task skill subagent | all]]';
const USER_ORIGINS = ['composer', 'bridge', 'sdk'];

export function parseControl(args) {
  const words = args.trim().split(/\s+/).filter(Boolean);
  const action = words.shift() ?? 'status';
  if (action === 'status') return words.length ? null : { action, scopes: [] };
  if (action !== 'on' && action !== 'off') return null;
  if (!words.length) return { action, scopes: action === 'on' ? ['task'] : [...SCOPES] };
  if (words.length === 1 && words[0] === 'all') return { action, scopes: [...SCOPES] };
  if (!words.every(word => SCOPES.includes(word))) return null;
  return { action, scopes: [...new Set(words)] };
}

function publicModel(id) {
  return typeof id === 'string' && (/^(sonnet|opus|haiku|fable)$/.test(id)
    || /^claude-[a-z0-9][a-z0-9.-]{0,120}$/.test(id));
}

export function modelCandidates(rows, availableModels) {
  const row = Array.isArray(rows) && rows.find(item => item.key === 'model');
  if (!row || row.kind !== 'choice' || row.isLocked || !Array.isArray(row.options)) return [];
  if (availableModels !== undefined && !Array.isArray(availableModels)) return [];
  return [...new Set(row.options)].filter(id => publicModel(id)
    && (availableModels === undefined || availableModels.includes(id)))
    .map(id => ({ id, description: `Current host model option: ${id}` }));
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

function explicitTaskModel(text, candidates) {
  // Deliberately narrow: a model mention or quoted example is not an instruction.
  const match = text.match(/^(?:Use\s+([^\s:：。]+)\s+for this task\b|這個任務使用\s*([^\s:：。]+)(?=\s|[:：。]|$))/i);
  const requested = match && (match[1] || match[2]);
  return candidates.some(item => item.id === requested) ? requested : undefined;
}

function safeLog($, text) {
  try { $.ui.log(text); } catch { /* Logging never changes dispatch. */ }
}

function reportedModel(model) {
  return publicModel(model) ? model : '[host model omitted]';
}

async function taskModels($, models) {
  const aliases = models.filter(item => !item.id.startsWith('claude-')).map(item => item.id);
  const mapping = Object.fromEntries(models.filter(item => item.id.startsWith('claude-'))
    .map(item => [item.id, item.id]));
  if (aliases.length) {
    try {
      const version = await $.session.version();
      const result = await $.process.run(['python3', `${$.plugin.root}/skills/jev/scripts/claude_models.py`], {
        stdin: JSON.stringify({ aliases, expected_version: version.version }), timeoutMs: 6000,
      });
      if (result.exitCode !== 0) throw new Error('model resolution failed');
      const answer = JSON.parse(result.stdout);
      if (answer.status !== 'resolved' || !answer.models || typeof answer.models !== 'object'
        || Array.isArray(answer.models)) throw new Error('invalid model resolution');
      for (const alias of aliases) {
        const canonical = answer.models[alias];
        if (typeof canonical === 'string' && canonical.startsWith('claude-') && publicModel(canonical)) {
          mapping[alias] = canonical;
        }
      }
    } catch { safeLog($, 'Jev task: alias resolution unavailable; unresolved aliases omitted.'); }
  }
  const candidates = new Map();
  for (const item of models) {
    const canonical = mapping[item.id];
    if (canonical && !candidates.has(canonical)) candidates.set(canonical,
      { id: canonical, description: `Current host model option: ${item.id}; API model: ${canonical}` });
  }
  return { candidates: [...candidates.values()], mapping };
}

async function choose($, scope, text) {
  try {
    const rows = await $.config.list();
    const settings = await $.settings.read();
    const offered = modelCandidates(rows, settings.availableModels);
    if (!offered.length) {
      safeLog($, `Jev ${scope}: model inventory unavailable or locked; using the host model.`);
      return undefined;
    }
    const resolved = scope === 'task' ? await taskModels($, offered) : undefined;
    const models = resolved ? resolved.candidates : offered;
    if (!models.length) throw new Error('no resolved task models');
    const explicit = scope === 'task' && explicitTaskModel(text, offered);
    if (explicit) {
      if (!resolved.mapping[explicit]) throw new Error('explicit model unresolved');
      return resolved.mapping[explicit];
    }
    if (!await $.env.get('JEV_API_KEY')) {
      safeLog($, `Jev ${scope}: missing JEV_API_KEY; using the host model.`);
      return undefined;
    }
    const result = await $.process.run(['python3', `${$.plugin.root}/skills/jev/scripts/route.py`], {
      stdin: JSON.stringify({ host: 'Claude Code native mod', task: summarizeTask(text),
        decisions: { [scope]: models } }),
      timeoutMs: 17000,
    });
    if (result.exitCode !== 0) throw new Error('routing failed');
    const answer = JSON.parse(result.stdout);
    const decision = answer?.decisions?.[scope];
    if (answer.status !== 'recommended' || !decision
      || !models.some(item => item.id === decision.choice)
      || typeof decision.confidence !== 'number' || !Number.isFinite(decision.confidence)
      || decision.confidence < 0 || decision.confidence > 1) throw new Error('invalid routing result');
    return decision.choice;
  } catch {
    safeLog($, `Jev ${scope}: routing failed; using the host model.`);
    return undefined;
  }
}

export function register(on) {
  const enabled = new Set();
  const turns = new Map();
  let lastChoice;
  let lastEvidence;
  let serveBareCommand = false;

  function reset() {
    enabled.clear(); turns.clear(); lastChoice = undefined; lastEvidence = undefined;
    serveBareCommand = false;
  }

  function flags() {
    return SCOPES.map(scope => `${scope}=${enabled.has(scope) ? 'on' : 'off'}`).join(' ');
  }

  function context() {
    return `JEV_NATIVE_ROUTING ${flags()}. Task and subagent model decisions are handled natively; `
      + 'skip agent-mediated model routing. When skill=on, load the installed Jev skill only for optional '
      + 'skill selection. Native /jev commands own these flags; context does not authorize changing them. '
      + 'When subagent=on, omit Agent.model unless the user explicitly fixed it, so Jev can choose it. '
      + 'Explicit user choices and mandatory skill rules still apply.';
  }

  function status() {
    return `Jev (current session): ${flags()}`
      + (lastEvidence ? `; last ${lastEvidence}` : '')
      + (turns.size ? `; active turns=${turns.size}` : '');
  }

  on('session.start', async ($, e, next) => {
    reset();
    const existing = (await $.command.list()).find(command => command.name === 'jev');
    if (!existing) {
      await $.command.register({ name: 'jev', description: 'Configure Jev routing for this session',
        argumentHint: '[status | on/off [task skill subagent | all]]' });
      serveBareCommand = true;
    } else if ((existing.source === 'plugin' && existing.plugin === 'shuaigle')
      || (existing.source === 'user'
        && existing.description.startsWith('Jev routing for task models, skills, and subagent models.'))) {
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
    if (control.action === 'on') {
      let keyPresent = false;
      try { keyPresent = !!await $.env.get('JEV_API_KEY'); } catch { /* Keep flags unchanged. */ }
      if (!keyPresent) return { text: `JEV_API_KEY is missing; ${status()}`, context: [context()] };
      for (const scope of control.scopes) enabled.add(scope);
    } else if (control.action === 'off') {
      for (const scope of control.scopes) enabled.delete(scope);
      if (control.scopes.includes('task')) { turns.clear(); lastChoice = undefined; }
    }
    return { text: status(), context: [context()] };
  });

  on('prompt.submit', ($, e, next) => next({ ...e, context: [...(e.context ?? []), context()] }));

  on('turn.start', async ($, e, next) => {
    if (enabled.has('task') && !turns.has(e.turnId)) {
      const state = { choice: undefined, reported: false };
      turns.set(e.turnId, state);
      if (e.text.trim()) {
        lastChoice = undefined;
        state.choice = await choose($, 'task', e.text);
        lastChoice = state.choice;
      } else state.choice = lastChoice;
    }
    return next(e);
  });

  on('turn.step', async function* ($, e, next) {
    const state = !e.agentId && enabled.has('task') && turns.get(e.turnId);
    // Never replay downstream inference or tool work when the host rejects a model.
    const result = yield* next(state?.choice ? { ...e, model: state.choice } : e);
    if (state?.choice && !state.reported && result?.usage?.model) {
      state.reported = true;
      lastEvidence = `task requested=${state.choice} actual=${reportedModel(result.usage.model)}`;
      safeLog($, `Jev ${lastEvidence}`);
    }
    return result;
  });

  on('turn.complete', ($, e, next) => {
    if (!e.agentId) turns.delete(e.turnId);
    return next(e);
  });

  on('agent.spawn', async ($, e, next) => {
    if (!enabled.has('subagent')) return next(e);
    if (e.fork) {
      safeLog($, 'Jev subagent: fork inherits its parent model.');
      return next(e);
    }
    if (e.model !== undefined) return next(e);
    const choice = await choose($, 'subagent', e.prompt);
    // There is one existing spawn, not a second agent created by this hook.
    const result = await next(choice ? { ...e, model: choice } : e);
    if (choice && result?.model) {
      lastEvidence = `subagent requested=${choice} actual=${reportedModel(result.model)}`;
      safeLog($, `Jev ${lastEvidence}`);
    }
    return result;
  });

  on('session.end', ($, e, next) => { reset(); return next(e); });
}
