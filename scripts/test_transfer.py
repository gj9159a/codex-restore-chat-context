import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('transfer.py')
spec = importlib.util.spec_from_file_location('transfer', MODULE)
transfer = importlib.util.module_from_spec(spec) if MODULE.exists() else None
if transfer:
    spec.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(transfer, 'snapshot/page/verification helper is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'rollout-source.jsonl'

    def write(self, rows, source=None):
        target = source or self.source
        target.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        return target

    def meta(self, **extra):
        return {'type': 'session_meta', 'payload': {'id': 'source-id', 'cwd': 'old', **extra}}

    def checkpoint(self, ordinal, name='latest'):
        return {'type': 'compacted', 'ordinal': ordinal, 'timestamp': f'2026-10-30T00:00:{ordinal:02d}Z', 'payload': {
            'replacement_history': [
                {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'retained-user-requirement'}]},
                {'type': 'configuration_update', 'reasoning': {'effort': 'low'}},
                {'type': 'compaction', 'id': name, 'encrypted_content': 'opaque-' + name}],
            'replacement_history_metadata': [{}, {}, {'compaction_model_hash': 'example-hash'}],
            'resume_metadata': {'previous_turn_settings': {'model': 'test-model', 'comp_hash': 'example-hash'}}}}

    def message(self, ordinal, text):
        return {'type': 'response_item', 'ordinal': ordinal, 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}}

    def prepare(self, rows, page_chars=160):
        self.write(rows)
        return transfer.prepare(self.source, 'source-id', 'Точное название', self.root / 'bundle', page_chars)

    def test_uses_last_checkpoint_and_preserves_retained_user_messages(self):
        manifest = self.prepare([self.meta(), self.checkpoint(1, 'old'), self.message(2, 'before-latest'), self.checkpoint(3), self.message(4, 'after-latest')])
        replay = [json.loads(line) for line in Path(manifest['recovery_rollout']).read_text(encoding='utf-8').splitlines()]
        history = replay[1]['payload']['replacement_history']
        self.assertEqual(manifest['compaction_id'], 'latest')
        self.assertEqual(manifest['model'], 'test-model')
        self.assertEqual(manifest['compaction_model_hash'], 'example-hash')
        self.assertIn('retained-user-requirement', json.dumps(history))
        self.assertNotIn('configuration_update', [r['type'] for r in history])
        tail = Path(manifest['tail_raw']).read_text(encoding='utf-8')
        self.assertIn('after-latest', tail)
        self.assertNotIn('before-latest', tail)

    def test_large_tool_output_is_preserved_across_pages_and_acknowledged(self):
        output = 'начало\n' + 'ф' * 31000 + '\nКОНЕЦ_ВЫВОДА'
        manifest = self.prepare([self.meta(), self.checkpoint(1), {'type': 'response_item', 'ordinal': 2, 'payload': {'type': 'function_call_output', 'call_id': 'call1', 'output': output}}], page_chars=1000)
        bundle = self.root / 'bundle'
        pages = [transfer.read_page(bundle, n) for n in range(1, len(manifest['pages']) + 1)]
        joined = ''.join(p['text'] for p in pages)
        parsed = [json.loads(s) for s in joined.splitlines()]
        self.assertEqual(next(r['payload']['output'] for r in parsed if r.get('payload', {}).get('type') == 'function_call_output'), output)
        self.assertFalse(transfer.verify(bundle)['tail_fully_acknowledged'])
        for page in pages:
            transfer.ack_page(bundle, page['index'], page['sha256'], 'прочитано')
        status = transfer.verify(bundle)
        self.assertTrue(status['tail_fully_acknowledged'])
        self.assertTrue(status['source_unchanged'])

    def test_wrong_ack_hash_and_tampered_page_are_rejected(self):
        self.prepare([self.meta(), self.checkpoint(1), self.message(2, 'hello')])
        bundle = self.root / 'bundle'
        with self.assertRaises(ValueError):
            transfer.ack_page(bundle, 1, 'incorrect', 'read')
        manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
        (bundle / manifest['pages'][0]['path']).write_text('tampered', encoding='utf-8')
        with self.assertRaises(ValueError):
            transfer.read_page(bundle, 1)

    def test_new_source_messages_prevent_current_coverage_claim(self):
        self.prepare([self.meta(), self.checkpoint(1), self.message(2, 'first')])
        with self.source.open('a', encoding='utf-8') as f:
            f.write(json.dumps(self.message(3, 'new')) + '\n')
        status = transfer.verify(self.root / 'bundle')
        self.assertFalse(status['source_unchanged'])
        self.assertTrue(status['new_source_data'])

    def test_standalone_injected_compaction_is_selected(self):
        standalone = {'type': 'response_item', 'ordinal': 3, 'timestamp': '2026-10-31T00:00:00Z', 'payload': {'type': 'compaction', 'id': 'injected', 'encrypted_content': 'opaque'}}
        manifest = self.prepare([self.meta(), self.checkpoint(1), self.message(2, 'before-injection'), standalone, self.message(4, 'after')])
        self.assertEqual(manifest['compaction_id'], 'injected')
        self.assertEqual(manifest['tail_records'], 1)

    def test_without_compaction_reads_full_history(self):
        manifest = self.prepare([self.meta(), self.message(1, 'whole-chat')])
        self.assertEqual(manifest['mode'], 'full-history')
        self.assertIsNone(manifest['recovery_rollout'])
        self.assertIn('whole-chat', Path(manifest['tail_raw']).read_text(encoding='utf-8'))

    def test_missing_parent_segment_is_not_silently_treated_as_full_history(self):
        self.write([self.meta(history_mode='paginated', history_base={'thread_id': 'missing-parent', 'end_ordinal_exclusive': 10}), self.message(10, 'late')])
        with self.assertRaisesRegex(ValueError, 'parent|предыдущ'):
            transfer.prepare(self.source, 'source-id', 'title', self.root / 'bundle', 200)

    def test_parent_segment_tail_is_included_before_current_segment(self):
        parent = self.root / 'rollout-parent-id.jsonl'
        self.write([self.meta(), self.checkpoint(1), self.message(2, 'parent-tail'), self.message(5, 'outside-boundary')], parent)
        self.write([self.meta(history_base={'thread_id': 'parent-id', 'end_ordinal_exclusive': 5}), self.message(5, 'current-tail')])
        manifest = transfer.prepare(self.source, 'source-id', 'title', self.root / 'bundle', 200)
        tail = Path(manifest['tail_raw']).read_text(encoding='utf-8')
        self.assertEqual(manifest['tail_records'], 2)
        self.assertLess(tail.index('parent-tail'), tail.index('current-tail'))
        self.assertNotIn('outside-boundary', tail)

    def test_malformed_json_and_wrong_thread_fail_without_claiming_success(self):
        self.write([self.meta(id='another-id'), self.checkpoint(1)])
        with self.assertRaises(ValueError):
            transfer.prepare(self.source, 'source-id', 'title', self.root / 'wrong', 200)
        self.source.write_text('{broken\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            transfer.prepare(self.source, 'source-id', 'title', self.root / 'broken', 200)

    def test_opaque_fields_are_reported_but_raw_tail_is_lossless(self):
        record = {'type': 'response_item', 'ordinal': 2, 'payload': {'type': 'reasoning', 'encrypted_content': 'secret-cipher', 'summary': [{'text': 'readable-summary'}]}}
        manifest = self.prepare([self.meta(), self.checkpoint(1), record])
        raw = Path(manifest['tail_raw']).read_text(encoding='utf-8')
        pages = ''.join(transfer.read_page(self.root / 'bundle', n)['text'] for n in range(1, len(manifest['pages']) + 1))
        self.assertIn('secret-cipher', raw)
        self.assertNotIn('secret-cipher', pages)
        self.assertIn('readable-summary', pages)
        self.assertTrue(manifest['limitations'])

    def test_zstd_source_is_read_without_modifying_archive(self):
        import zstandard
        source = self.root / 'rollout-source.jsonl.zst'
        raw = ''.join(json.dumps(r) + '\n' for r in [self.meta(), self.checkpoint(1), self.message(2, 'compressed-tail')]).encode()
        source.write_bytes(zstandard.ZstdCompressor().compress(raw))
        before = source.read_bytes()
        manifest = transfer.prepare(source, 'source-id', 'title', self.root / 'bundle', 200)
        self.assertIn('compressed-tail', Path(manifest['tail_raw']).read_text(encoding='utf-8'))
        self.assertEqual(source.read_bytes(), before)

    def test_empty_tail_needs_no_page_acknowledgment(self):
        checkpoint = self.checkpoint(1)
        checkpoint['payload']['replacement_history'].pop(1)
        self.prepare([self.meta(), checkpoint])
        status = transfer.verify(self.root / 'bundle')
        self.assertTrue(status['tail_fully_acknowledged'])
        self.assertFalse(status['compaction_restored'])

    def test_legacy_text_summary_needs_no_encrypted_recovery(self):
        manifest = self.prepare([self.meta(), {'type': 'compacted', 'ordinal': 1, 'payload': {'message': 'legacy-summary'}}, self.message(2, 'tail')])
        self.assertIsNone(manifest['recovery_rollout'])
        self.assertIn('legacy-summary', (self.root / 'bundle' / 'recovered-compaction.md').read_text(encoding='utf-8'))

    def test_checkpoint_without_resume_metadata_uses_its_model_not_later_model(self):
        checkpoint = self.checkpoint(2)
        checkpoint['payload'].pop('resume_metadata')
        manifest = self.prepare([self.meta(), {'type': 'turn_context', 'ordinal': 1, 'payload': {'model': 'original-model'}}, checkpoint, {'type': 'turn_context', 'ordinal': 3, 'payload': {'model': 'later-model'}}])
        self.assertEqual(manifest['model'], 'original-model')

    def test_retained_tool_results_are_exported_for_mandatory_reading(self):
        checkpoint = self.checkpoint(1)
        checkpoint['payload']['replacement_history'].insert(0, {'type': 'function_call_output', 'call_id': 'retained-call', 'output': 'IMPORTANT-RETAINED-RESULT'})
        manifest = self.prepare([self.meta(), checkpoint, self.message(2, 'new')])
        text = ''.join(transfer.read_page(self.root / 'bundle', i)['text'] for i in range(1, len(manifest['pages']) + 1))
        self.assertIn('IMPORTANT-RETAINED-RESULT', text)
        self.assertLess(text.index('IMPORTANT-RETAINED-RESULT'), text.index('new'))

    def test_protocol_completion_alone_does_not_confirm_semantic_recovery(self):
        self.prepare([self.meta(), self.checkpoint(1)])
        bundle = self.root / 'bundle'
        (bundle / 'recovery-report.json').write_text(json.dumps({'status': 'completed', 'model': 'test-model', 'tool_calls': 0, 'server_requests': 0}), encoding='utf-8')
        (bundle / 'recovered-compaction.md').write_text('Контекст недоступен.', encoding='utf-8')
        self.assertFalse(transfer.verify(bundle)['compaction_restored'])

    def test_semantic_receipt_is_bound_to_answer_and_requires_specific_evidence(self):
        manifest = self.prepare([self.meta(), self.checkpoint(1)])
        bundle = self.root / 'bundle'
        (bundle / 'recovery-report.json').write_text(json.dumps({'status': 'completed', 'model': 'test-model', 'tool_calls': 0, 'server_requests': 0}), encoding='utf-8')
        answer = bundle / 'recovered-compaction.md'
        answer.write_text('Согласовано правило: keep-X.', encoding='utf-8')
        with self.assertRaises(ValueError):
            transfer.confirm_recovery(bundle, transfer.digest(answer), '')
        transfer.confirm_recovery(bundle, transfer.digest(answer), 'Восстановлено конкретное правило keep-X.')
        self.assertTrue(transfer.verify(bundle)['compaction_restored'])
        for i in range(1, len(manifest['pages']) + 1):
            page = transfer.read_page(bundle, i)
            transfer.ack_page(bundle, i, page['sha256'], 'Все дополнительные retained-элементы прочитаны.')
        self.assertTrue(transfer.verify(bundle)['coverage_complete'])
        answer.write_text('other text', encoding='utf-8')
        self.assertFalse(transfer.verify(bundle)['compaction_restored'])

    def test_known_retained_history_gap_blocks_full_coverage_even_after_success(self):
        standalone = {'type': 'response_item', 'ordinal': 2, 'payload': {'type': 'compaction', 'id': 'injected', 'encrypted_content': 'opaque'}}
        manifest = self.prepare([self.meta(), {'type': 'turn_context', 'ordinal': 1, 'payload': {'model': 'test-model'}}, standalone])
        bundle = self.root / 'bundle'
        (bundle / 'recovery-report.json').write_text(json.dumps({'status': 'completed', 'model': 'test-model', 'tool_calls': 0, 'server_requests': 0}), encoding='utf-8')
        answer = bundle / 'recovered-compaction.md'
        answer.write_text('Исторический факт X.', encoding='utf-8')
        transfer.confirm_recovery(bundle, transfer.digest(answer), 'Конкретный факт X восстановлен.')
        status = transfer.verify(bundle)
        self.assertTrue(status['compaction_restored'])
        self.assertTrue(status['tail_fully_acknowledged'])
        self.assertFalse(status['coverage_complete'])
        self.assertTrue(status['completeness_gaps'])


if __name__ == '__main__':
    unittest.main()
