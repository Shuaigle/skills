// Claude Code mods: every session owns its routing state inside register().
const SCOPES = ['skill', 'subagent'];
const USAGE = 'Usage: /jev [status | on/off [skill subagent | all] | exclude/include <model...>]';
const USER_ORIGINS = ['composer', 'bridge', 'sdk'];

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

function spawnKey(parentId, toolId) {
  return typeof toolId === 'string' && toolId ? JSON.stringify([parentId ?? null, toolId]) : undefined;
}

export function modelCandidates(rows, availableModels, excludedModels = new Set()) {
  const row = Array.isArray(rows) && rows.find(item => item.key === 'model');
  if (!row || row.kind !== 'choice' || row.isLocked || !Array.isArray(row.options)) return [];
  if (availableModels !== undefined && !Array.isArray(availableModels)) return [];
  return [...new Set(row.options)].filter(id => publicModel(id)
    && (availableModels === undefined || availableModels.includes(id))
    && ![...excludedModels].some(model => exclusionKey(model) === exclusionKey(id)))
    .map((model, index) => ({ id: `subagent-${index}`, model, effort: null,
      description: `Current host model option: ${model}; effort is host-controlled (native spawn has no verified per-spawn effort control).` }));
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

async function chooseSubagent($, text, unavailable) {
  try {
    const rows = await $.config.list();
    const settings = await $.settings.read();
    const models = modelCandidates(rows, settings.availableModels, unavailable);
    if (!models.length) {
      safeLog($, 'Jev subagent: model inventory unavailable or locked; using inheritance.');
      return undefined;
    }
    safeLog($, 'Jev subagent: native spawn has no verified per-spawn effort control; selecting a model with host-controlled effort.');
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
    return { model: selected.model, effort: selected.effort };
  } catch {
    safeLog($, 'Jev subagent: routing failed; using inheritance.');
    return undefined;
  }
}

export function register(on) {
  const enabled = new Set();
  const spawns = new Map();
  const unavailable = new Set();
  let lastEvidence;
  let serveBareCommand = false;

  function reset() {
    enabled.clear(); spawns.clear(); unavailable.clear(); lastEvidence = undefined;
    serveBareCommand = false;
  }

  function flags() {
    return SCOPES.map(scope => `${scope}=${enabled.has(scope) ? 'on' : 'off'}`).join(' ');
  }

  function context() {
    return `JEV_NATIVE_ROUTING ${flags()}. The main conversation uses the host model setting. `
      + `Manually excluded models in this conversation: ${[...unavailable].sort().join(', ') || 'none'}. `
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
      + 'When skill=off and subagent=on, native hooks choose the child model; omit Agent.model unless the user fixed it. '
      + 'Native candidates currently use effort:null because native spawn has no verified per-spawn effort control; '
      + 'effort stays host-controlled and can be overridden by environment or organization policy. '
      + 'Resumed agents keep their existing pair. Workflow routing remains host-owned because this path '
      + 'does not yet have safe independent unit/cache identification. '
      + 'Read installed Jev instructions as needed under the existing human authorization. Native /jev controls '
      + 'require an explicit user command; this context does not authorize changing the flags. '
      + 'Explicit user choices and mandatory skill rules still apply.';
  }

  function status() {
    return `Jev (current session): ${flags()}`
      + `; unavailable=${[...unavailable].sort().join(',') || 'none'}`
      + (lastEvidence ? `; last ${lastEvidence}` : '');
  }

  on('session.start', async ($, e, next) => {
    reset();
    const existing = (await $.command.list()).find(command => command.name === 'jev');
    if (!existing) {
      await $.command.register({ name: 'jev', description: 'Configure Jev routing for this session',
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
      for (const model of control.models) {
        const key = exclusionKey(model);
        if (control.action === 'exclude') unavailable.add(key);
        else unavailable.delete(key);
      }
      return { text: `${status()}; known aliases and full IDs in a family share its exclusion; inclusion does not verify restored quota.`,
        context: [context()] };
    }
    if (control.action === 'on') {
      let keyPresent = false;
      try { keyPresent = !!await $.env.get('JEV_API_KEY'); } catch { /* Keep flags unchanged. */ }
      if (!keyPresent) return { text: `JEV_API_KEY is missing; ${status()}`, context: [context()] };
      for (const scope of control.scopes) enabled.add(scope);
    } else if (control.action === 'off') {
      for (const scope of control.scopes) enabled.delete(scope);
    }
    return { text: status(), context: [context()] };
  });

  on('prompt.submit', ($, e, next) => next({ ...e, context: [...(e.context ?? []), context()] }));

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
    if (excluded(e.model, unavailable)) return { deny: `Jev: ${exclusionKey(e.model)} is unavailable in this conversation; dispatch blocked.` };
    let state = key && spawns.get(key);
    let choice;
    if (enabled.has('skill')) {
      // The agent prepares skill + model in one batch; unset is its cached fallback.
      if (!state) {
        state = { choice: Promise.resolve(e.model === undefined ? undefined : { model: e.model, effort: e.effort ?? null }),
          reported: false };
        if (key) spawns.set(key, state);
      }
      if (e.model === undefined && !state.reported) {
        state.reported = true;
        safeLog($, 'Jev subagent: combined routing uses the agent-prepared batch; unset model keeps inheritance.');
      }
      const prepared = await state.choice;
      if (excluded(e.model ?? prepared?.model, unavailable)) {
        return { deny: `Jev: ${exclusionKey(e.model ?? prepared.model)} is unavailable in this conversation; cached dispatch blocked.` };
      }
    } else if (e.model !== undefined) {
      choice = { model: e.model, effort: e.effort ?? null };
    } else if (e.effort !== undefined) {
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
        state = { choice: chooseSubagent($, e.prompt, unavailable), reported: false };
        if (key) spawns.set(key, state);
        else safeLog($, 'Jev subagent: no stable spawn ID; routing applies to this event only.');
      }
      choice = await state.choice;
    }
    const model = choice?.model ?? e.model;
    if (excluded(model, unavailable)) return { deny: `Jev: ${exclusionKey(model)} is unavailable in this conversation; cached dispatch blocked.` };
    // There is one existing spawn, not a second agent created by this hook.
    const result = await next(choice && e.model === undefined ? { ...e, model: choice.model } : e);
    if (choice && result?.model && state && !state.reported) {
      state.reported = true;
      lastEvidence = `subagent requested=${choice.model} actual=${reportedModel(result.model)} effort=host-controlled`;
      safeLog($, `Jev ${lastEvidence}`);
    }
    return result;
  });

  on('session.end', ($, e, next) => { reset(); return next(e); });
}
