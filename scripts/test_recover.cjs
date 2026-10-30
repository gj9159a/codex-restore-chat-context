const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

if (process.argv[2] === '--mock') {
  const scenario = process.argv[3];
  const send = message => process.stdout.write(JSON.stringify(message) + '\n');
  const log = message => fs.appendFileSync(process.env.RECOVERY_MOCK_LOG, JSON.stringify(message) + '\n');
  log({ mock_pid: process.pid });
  require('node:readline').createInterface({ input: process.stdin }).on('line', line => {
    const m = JSON.parse(line); log(m);
    if (m.error) return;
    if (m.method === 'initialize' && scenario === 'exit') return process.exit(3);
    if (m.method === 'initialize' && scenario === 'timeout') return;
    if (m.method === 'initialize' && scenario === 'rpc-error') return send({ id: m.id, error: { code: -1, message: 'SECRET-CIPHERTEXT' } });
    if (m.method === 'initialize') return send({ id: m.id, result: {} });
    if (m.method === 'thread/resume') return send({ id: m.id, result: { thread: { id: m.params.threadId }, model: scenario === 'model-mismatch' ? 'other-model' : 'mock-model' } });
    if (m.method === 'turn/interrupt') return send({ id: m.id, result: {} });
    if (m.method !== 'turn/start') return;
    send({ id: m.id, result: { turn: { id: 'turn-1' } } });
    if (scenario === 'turn-timeout') return;
    if (scenario === 'request') return send({ id: 1000, method: 'item/commandExecution/requestApproval', params: {} });
    if (scenario === 'tool') return send({ method: 'item/started', params: { item: { type: 'commandExecution', id: 'tool-1' } } });
    if (scenario === 'error') return send({ method: 'error', params: { error: { message: 'SECRET-CIPHERTEXT' } } });
    if (scenario !== 'missing') send({ method: 'item/completed', params: { item: { type: 'agentMessage', phase: 'final_answer', text: 'Исторический контекст: принято решение А.' } } });
    const failed = scenario === 'failed' || (scenario === 'verify-failed' && fs.readFileSync(process.env.RECOVERY_MOCK_LOG, 'utf8').split('\n').filter(line => line.includes('"method":"turn/start"')).length > 1);
    send({ method: 'turn/completed', params: { turn: { id: 'turn-1', status: failed ? 'failed' : 'completed', error: failed ? { message: 'SECRET-CIPHERTEXT' } : null } } });
    if (scenario === 'late-tool') send({ method: 'item/started', params: { item: { type: 'webSearch' } } });
  });
} else {
  const test = require('node:test');
  for (const scenario of ['success', 'model-unknown', 'model-mismatch', 'failed', 'exit', 'missing', 'timeout', 'turn-timeout', 'request', 'tool', 'late-tool', 'error', 'rpc-error', 'verify-failed']) {
    test(scenario, async () => {
      const { recover } = require('./recover.cjs');
      const bundle = fs.mkdtempSync(path.join(os.tmpdir(), 'recover-test-'));
      try {
        const rollout = path.join(bundle, 'copy.jsonl'); fs.writeFileSync(rollout, '{}\n');
        fs.writeFileSync(path.join(bundle, 'manifest.json'), JSON.stringify({ recovery_thread_id: '12345678-1234-4234-8234-123456789abc', model: scenario === 'model-unknown' ? undefined : 'mock-model', recovery_rollout: rollout, source_thread_id: 'source', source_title: 'source', compaction_timestamp: '2026-01-01', compaction_model_hash: 'hash' }));
        const log = path.join(bundle, 'mock.jsonl');
        const result = await recover({ bundle, timeoutSeconds: 0.5, verifyResume: ['success', 'verify-failed'].includes(scenario), launch: { executable: process.execPath, args: [__filename, '--mock', scenario], env: { ...process.env, RECOVERY_MOCK_LOG: log } } });
        assert.equal(result.success, scenario === 'success');
        const report = JSON.parse(fs.readFileSync(path.join(bundle, 'recovery-report.json')));
        assert.equal(report.status, scenario === 'success' ? 'completed' : 'failed');
        assert.equal(report.semantic_verified, false);
        assert.ok(!JSON.stringify(report).includes('SECRET-CIPHERTEXT'));
        const messages = fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse) : [];
        if (scenario === 'model-unknown') {
          assert.deepEqual(report.errors, ['source_model_unknown']);
          assert.equal(messages.length, 0);
          assert.equal(report.runs.length, 0);
        }
        if (scenario === 'model-mismatch') {
          assert.deepEqual(report.errors, ['source_model_mismatch']);
          assert.equal(messages.filter(m => m.method === 'thread/resume').length, 1);
          assert.ok(!messages.some(m => m.method === 'turn/start'));
        }
        for (const message of messages.filter(m => m.mock_pid)) assert.throws(() => process.kill(message.mock_pid, 0), { code: 'ESRCH' });
        if (scenario === 'success') {
          assert.equal(report.model, 'mock-model');
          assert.equal(report.tool_calls, 0);
          assert.ok(fs.readFileSync(path.join(bundle, 'recovered-compaction.md'), 'utf8').includes('решение А'));
          assert.ok(fs.existsSync(path.join(bundle, 'verify-response.md')));
          assert.equal(messages.filter(m => m.method === 'thread/resume').length, 2);
          for (const m of messages.filter(m => m.method === 'thread/resume')) {
            assert.equal(m.params.model, 'mock-model');
            assert.equal(m.params.sandbox, 'read-only'); assert.equal(m.params.approvalPolicy, 'never');
            assert.equal(m.params.config.web_search, 'disabled');
          }
        }
        if (scenario === 'request') assert.ok(messages.some(m => m.id === 1000 && m.error));
        if (['request', 'tool'].includes(scenario)) assert.ok(messages.some(m => m.method === 'turn/interrupt'));
      } finally { fs.rmSync(bundle, { recursive: true, force: true }); }
    });
  }
  test('CLI failure is nonzero and emits only short JSON', () => {
    const result = require('node:child_process').spawnSync(process.execPath, [path.join(__dirname, 'recover.cjs'), '--unknown'], { encoding: 'utf8', windowsHide: true });
    assert.equal(result.status, 1);
    assert.deepEqual(JSON.parse(result.stdout), { success: false, model: null, text_chars: 0 });
    assert.equal(result.stderr, '');
  });
}
