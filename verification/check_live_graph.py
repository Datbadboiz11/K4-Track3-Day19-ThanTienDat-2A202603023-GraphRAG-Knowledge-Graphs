"""Read-only checks on a fully built KG. Does not invoke any model or reset the graph."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.graph import Neo4jGraph


def check_graph(graph):
    questions = json.loads(Path('data/benchmark_kg.json').read_text(encoding='utf-8'))
    entries = {}
    for qid, docs in [('Q3', ['news-100260918080821054']), ('Q4', []),
                      ('Q5', ['news-100260917203001265']), ('Q6', [])]:
        q = next(q for q in questions if q['id'] == qid)
        facts = graph.context(q['question'], docs)
        entries[qid] = {'question': q['question'], 'doc_ids': docs, 'facts': facts,
                        'chars': sum(map(len, facts))}
    assert any('Điều 251' in f and '02 năm đến 07 năm' in f for f in entries['Q3']['facts'])
    assert any('Điều 255' in f and 'khoản 4' in f and 'chung thân' in f for f in entries['Q4']['facts'])
    assert any('Điều 250' in f and 'khoản 4' in f and '9600' in f for f in entries['Q5']['facts'])
    assert not any('Điều 251' in f or 'Điều 249' in f or 'Điều 255' in f for f in entries['Q5']['facts'])
    for name in ['Cái Quang Huy', 'Lê Minh Thành', 'Pháp y tâm thần']:
        assert any(name in f for f in entries['Q6']['facts'])
    assert not any('BLHS' in f for f in entries['Q6']['facts'])
    assert all(e['chars'] <= 9000 for e in entries.values())
    return {'stats': graph.stats(), 'contexts': entries}


if __name__ == '__main__':
    load_dotenv('.env')
    graph = Neo4jGraph(os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                       os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'password123'))
    try:
        evidence = check_graph(graph)
        Path('report/evidence/live_after.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Live context checks passed for Q3, Q4, Q5, Q6; no API calls.')
    finally:
        graph.close()
