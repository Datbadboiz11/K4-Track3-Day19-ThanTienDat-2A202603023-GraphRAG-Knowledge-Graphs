"""Update report tables only from an actual official benchmark result.

No benchmark output is edited or generated here. The finalize script calls this only
after the official paid benchmark and read-only live checks both succeed.
"""

import json
import re
from pathlib import Path


def parse_benchmark(path):
    text = Path(path).read_text(encoding='utf-8')
    sections = {}
    for title, following in [('index', '== Indexing (one-off)'), ('query', '== Querying (mean per question)')]:
        body = text.split(following, 1)[1].split('==', 1)[0].strip()
        sections[title] = body
    rows = {}
    pattern = r'^--- (Q\d+) \[([^\]]+)\] (flat|graph) recall=([0-9.]+) judge=(\d) ([0-9.]+)s\n(.*?)(?=^--- |\Z)'
    for m in re.finditer(pattern, text, flags=re.M | re.S):
        rows[(m[1], m[3])] = {'recall':float(m[4]), 'judge':int(m[5]), 'answer':m[7].strip()}
    if len(rows) != 12 or not text.startswith('Chat model:'):
        raise ValueError('Need 6 questions x 2 pipelines with judge; run unmodified bench_kg.py --judge')
    sections['index_values'] = {line.split()[0]:line.split()[1:]
                               for line in sections['index'].splitlines() if line.startswith(('flat ', 'graph '))}
    sections['query_values'] = {line.split()[0]:line.split()[1:]
                               for line in sections['query'].splitlines() if line.startswith(('flat ', 'graph '))}
    sections['header'] = text.splitlines()[0]
    sections['rows'] = rows
    return sections


def replace_block(text, name, content):
    start, end = f'<!-- {name}_START -->', f'<!-- {name}_END -->'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Missing unique report markers for {name}')
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + '\n' + content + '\n' + end + after


def main():
    data = parse_benchmark('ket_qua_benchmark_kg.txt')
    questions = json.loads(Path('data/benchmark_kg.json').read_text(encoding='utf-8'))
    traces = {p['question']:p for path in Path('report/evidence/traces').glob('*.json')
              for p in [json.loads(path.read_text(encoding='utf-8'))]}
    for q in questions:
        trace = traces.get(q['question'])
        if not trace or trace['answer'].strip() != data['rows'][(q['id'], 'graph')]['answer']:
            raise ValueError(f'Missing or stale generation trace for {q["id"]}; rerun finalize script')
    lines = ['## 1. Chi phí', '', data['header'], '', '```', '== Indexing (one-off)', data['index'],
             '', '== Querying (mean per question)', data['query'], '```', '',
             '| Chỉ số | Flat | Graph | Graph/Flat |', '| --- | ---: | ---: | ---: |']
    ix, qu = data['index_values'], data['query_values']
    for label, f, g in [('Indexing USD', ix['flat'][3], ix['graph'][3]),
                        ('Indexing giây', ix['flat'][4], ix['graph'][4]),
                        ('Mỗi câu USD', qu['flat'][4], qu['graph'][4]),
                        ('Mỗi câu giây', qu['flat'][5], qu['graph'][5]),
                        ('Mỗi câu input token', qu['flat'][2], qu['graph'][2])]:
        ratio = float(g)/float(f) if float(f) else float('inf')
        lines.append(f'| {label} | {f} | {g} | ×{ratio:.2f} |')
    lines += ['', f'Phần dựng KG tăng thêm {int(ix["graph"][1])-int(ix["flat"][1])} input token, '
              f'{int(ix["graph"][2])-int(ix["flat"][2])} output token và '
              f'${float(ix["graph"][3])-float(ix["flat"][3]):.5f}. '
              'Graph indexing đã bao gồm vector indexing; không gán toàn bộ input token cho LLM trích xuất.',
              '', '## 2. Từng câu hỏi', '', '| Câu | Loại | Flat recall / judge | Graph recall / judge | Nhận xét |',
              '| --- | --- | --- | --- | --- |']
    for q in questions:
        f, g = data['rows'][(q['id'],'flat')], data['rows'][(q['id'],'graph')]
        verdict = 'Graph hơn theo judge' if g['judge'] > f['judge'] else 'Flat hơn theo judge' if g['judge'] < f['judge'] else 'Judge bằng nhau'
        if q['id'] == 'Q5':
            verdict += '; ' + ('nêu đúng Điều 250' if 'Điều 250' in g['answer'] else 'chưa nêu đúng Điều 250')
        lines.append(f'| {q["id"]} | {q["type"]} | {f["recall"]:.2f} / {f["judge"]} | '
                     f'{g["recall"]:.2f} / {g["judge"]} | {verdict} |')
    lines += ['', 'Recall là tỷ lệ từ khóa, không phải tỷ lệ câu trả lời đúng. Judge 1/2 là đúng một phần. '
              'Đọc nguyên văn câu trả lời và traces để đánh giá; chỉ một lần đo trên 6 câu chưa đủ khái quát.',
              '', '### So sánh ontology gợi ý', '']
    baseline_path = Path('ket_qua_benchmark_kg.hint.txt')
    if baseline_path.exists():
        hint = parse_benchmark(baseline_path)
        final_signature = re.split(r' \| chunks=', data['header'], maxsplit=1)[0]
        hint_signature = re.split(r' \| chunks=', hint['header'], maxsplit=1)[0]
        if final_signature != hint_signature:
            raise ValueError('Hint and final benchmark provider/top_k/chunk_size differ')
        lines += ['| Câu | Hint graph recall / judge | Custom graph recall / judge |', '| --- | ---: | ---: |']
        for q in questions:
            h, g = hint['rows'][(q['id'],'graph')], data['rows'][(q['id'],'graph')]
            lines.append(f'| {q["id"]} | {h["recall"]:.2f} / {h["judge"]} | {g["recall"]:.2f} / {g["judge"]} |')
        lines += ['', 'Baseline là ontology gợi ý được hoàn thành theo HINT tại `experiments/hint_solution/`. '
                  'Hai lần chạy trích xuất lại độc lập nên chênh lệch còn chịu ảnh hưởng của LLM; '
                  'không coi đây là ablation chỉ thay đổi một biến.']
    else:
        lines += ['Chưa có file benchmark hint hợp lệ; chưa đủ bằng chứng để kết luận bonus cải thiện.']
    path = Path('report/REPORT_KG.md')
    report = path.read_text(encoding='utf-8')
    report = replace_block(report, 'BENCHMARK', '\n'.join(lines))
    report = replace_block(report, 'STATUS', 'Đã chạy benchmark chính thức với code cuối cùng; số liệu bên dưới lấy từ output thật. '
                           'Ảnh Neo4j cần kiểm tra riêng trong `report/img/`.')
    check_output = Path('report/evidence/check.txt').read_text(encoding='utf-8-sig').strip()
    tests = Path('report/evidence/tests.txt').read_text(encoding='utf-8-sig').strip()
    report = replace_block(report, 'CHECK', '```\n' + tests + '\n\n' + check_output + '\n```\n'
        'Truy xuất trên graph đầy đủ kiểm tra riêng trong `report/evidence/live_after.json`.')
    path.write_text(report, encoding='utf-8')
    ontology_path = Path('report/ONTOLOGY.md')
    ontology = ontology_path.read_text(encoding='utf-8')
    ontology = replace_block(ontology, 'VALIDATION',
        'Đã chạy benchmark LLM và kiểm tra truy xuất trên graph đầy đủ. Kết quả từng câu nằm trong '
        '`ket_qua_benchmark_kg.txt` và bảng báo cáo; competency questions mô tả khả năng thiết kế, '
        'không phải bảo đảm mọi đáp án LLM đúng.')
    if baseline_path.exists():
        baseline_text = ('Baseline tại `experiments/hint_solution/` đã chạy bằng benchmark gốc, kết quả '
            '`ket_qua_benchmark_kg.hint.txt`. So sánh từng câu có trong `REPORT_KG.md`. '
            'Hai lần trích xuất độc lập vẫn chịu biến động LLM; không tự kết luận đạt đủ bonus.')
    else:
        baseline_text = 'Chưa có benchmark hint hợp lệ; chưa đủ bằng chứng benchmark cho phần bonus.'
    ontology = replace_block(ontology, 'BASELINE', baseline_text)
    ontology_path.write_text(ontology, encoding='utf-8')
    readme_path = Path('README.md')
    readme = replace_block(readme_path.read_text(encoding='utf-8'), 'PROJECT_STATUS',
        '> **Bản cải tiến:** đã chạy benchmark với code cuối cùng; kết quả ở `ket_qua_benchmark_kg.txt` '
        'và `report/REPORT_KG.md`, traces ở `report/evidence/traces/`. '
        'Kiểm tra ba ảnh Neo4j riêng trước khi nộp bài.')
    readme_path.write_text(readme, encoding='utf-8')
    print('Updated report from unmodified official benchmark; validated all six answer traces.')


if __name__ == '__main__':
    main()
