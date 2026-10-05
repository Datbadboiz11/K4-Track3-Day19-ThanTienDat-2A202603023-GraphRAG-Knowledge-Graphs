"""Verify both paid endpoints before bench_kg.py can reset the local graph."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.graph import Neo4jGraph
from src.llm import MeteredLLM


def main():
    load_dotenv('.env')
    graph = Neo4jGraph(os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                       os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'password123'))
    try:
        llm = MeteredLLM()
        llm.embed('Kiểm tra kết nối embedding trước benchmark.')
        llm.chat('Trả về JSON {"ok":true} để kiểm tra kết nối.', json_mode=True)
        snapshot = {
            'nodes': graph.run('MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props'),
            'relationships': graph.run('MATCH (a)-[r]->(b) RETURN elementId(a) AS start, elementId(b) AS end, '
                                       'type(r) AS type, properties(r) AS props'),
            'constraints': graph.run('SHOW CONSTRAINTS'),
        }
        out = Path('report/evidence')
        out.mkdir(parents=True, exist_ok=True)
        (out/'graph_before_finalize.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (out/'preflight.json').write_text(json.dumps({'chat':llm.chat_model, 'embedding':llm.embedding_model,
            'calls':llm.usage.calls, 'estimated_usd':llm.usage.usd}, indent=2), encoding='utf-8')
        print('Chat, embedding and Neo4j connected. Saved graph snapshot. Preflight cost is separate from benchmark.')
    finally:
        graph.close()


if __name__ == '__main__':
    main()
