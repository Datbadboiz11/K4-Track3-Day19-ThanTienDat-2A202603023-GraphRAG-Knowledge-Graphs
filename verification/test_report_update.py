"""Report generation must reject incomplete measurements and ambiguous template updates."""

import pytest

from scripts.update_benchmark_report import parse_benchmark, replace_block


def test_reads_actual_archived_benchmark():
    data = parse_benchmark('report/archive/ket_qua_benchmark_kg.before.txt')
    assert data['rows'][('Q5', 'graph')]['judge'] == 1
    assert 'Điều 251' in data['rows'][('Q5', 'graph')]['answer']
    assert data['query_values']['graph'][0] == '0.69'


def test_rejects_benchmark_without_judge(monkeypatch):
    from pathlib import Path
    text = Path('report/archive/ket_qua_benchmark_kg.before.txt').read_text(encoding='utf-8')
    monkeypatch.setattr(Path, 'read_text', lambda self, **kwargs: text.replace(' judge=1', ''))
    with pytest.raises(ValueError):
        parse_benchmark('in-memory-incomplete-measurement.txt')


def test_report_markers_must_be_unique():
    with pytest.raises(ValueError):
        replace_block('no measurement markers', 'BENCHMARK', 'new values')
    assert replace_block('before<!-- X_START -->old<!-- X_END -->after', 'X', 'new') == \
        'before<!-- X_START -->\nnew\n<!-- X_END -->after'
