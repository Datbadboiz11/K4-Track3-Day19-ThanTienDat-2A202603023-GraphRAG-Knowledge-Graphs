"""Integration tests using manually curated source facts, not model-produced benchmark output.

Fixture nodes carry a unique prefix and are removed afterwards; production nodes are not reset.
"""

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

from src.graph import (Document, GraphRAGAgent, Neo4jGraph, build_graph, extract_news_cases,
                       load_markdown_docs)
from src import EmbeddingStore
from verification.check_live_graph import check_graph


def run():
    load_dotenv('.env')
    graph = Neo4jGraph(os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                       os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'password123'))
    prefix = 'verification-' + uuid.uuid4().hex[:8] + ':'
    news = {d.id: d for d in load_markdown_docs('data/drug_news')}
    # All fixture assertions come from the cited frozen source documents.
    fixtures = [
        ('news-100260918080821054', {'name':'Vụ góp tiền mua ma túy tại Hà Nội',
            'charges':['mua bán trái phép chất ma túy'],
            'people':[{'name':'Lê Minh Thành','charge':'mua bán trái phép chất ma túy','sentence':'36 tháng tù'}],
            'substances':[{'name':'MDMA','amount':'5 viên'}]}),
        ('news-100260920221957595', {'name':'Vụ Hoàng Nato và các đường dây ma túy',
            'charges':['tổ chức sử dụng trái phép chất ma túy','mua bán trái phép chất ma túy'],
            'people':[{'name':'Dương Minh Tuấn','aliases':['Hoàng Nato'],
                       'charge':'tổ chức sử dụng trái phép chất ma túy'},
                      {'name':'Kim Yu Young','charge':'mua bán trái phép chất ma túy'}],
            'substances':[{'name':'thuốc lắc','amount':''}]}),
        ('news-100260917203001265', {'name':'Vụ vận chuyển ma túy từ Đức qua Nội Bài',
            'charges':['vận chuyển trái phép chất ma túy'],
            'people':[{'name':'Cái Quang Huy','charge':'vận chuyển trái phép chất ma túy',
                       'substances':[{'name':'MDMA','amount':'hơn 9,6kg'}, {'name':'Ketamine','amount':'khoảng 406g'}]},
                      {'name':'Nguyễn Tiến Đạt','charge':'vận chuyển trái phép chất ma túy',
                       'substances':[{'name':'MDMA','amount':'gần 4,3kg'}]}],
            'substances':[{'name':'MDMA','amount':'hơn 9,6kg'}, {'name':'Ketamine','amount':'khoảng 406g'}]}),
        ('news-100260924105118645', {'name':'Vụ tại Viện Pháp y tâm thần Trung ương',
            'charges':['tổ chức sử dụng trái phép chất ma túy'],
            'people':[{'name':'Lê Văn Đông','charge':'tổ chức sử dụng trái phép chất ma túy'}],
            'substances':[{'name':'MDMA','amount':''}, {'name':'Ketamine','amount':''}]}),
    ]
    created_people = []
    try:
        build_graph(graph, load_markdown_docs('data/drug_law'), [], lambda _: '')
        for doc_id, raw in fixtures:
            case = extract_news_cases(news[doc_id], lambda _, raw=raw: json.dumps({'cases':[raw]}),
                                      [c['name'] for c in graph.run('MATCH (c:Crime) RETURN c.name AS name')])[0]
            case['id'] = prefix + case['id']
            # Isolate Person fixtures even if the live graph already contains the same names.
            for person in case['people']:
                name = person['name']
                person['name'] = prefix + name
                person['aliases'] = list(dict.fromkeys(person['aliases'] + [name]))
                created_people.append(person['name'])
            graph.add_news_case(case, news[doc_id])
        # Exercise cross-article identity and alias accumulation without changing source facts.
        first = extract_news_cases(news['news-100260920221957595'],
            lambda _: json.dumps({'cases':[fixtures[1][1]]}),
            [c['name'] for c in graph.run('MATCH (c:Crime) RETURN c.name AS name')])[0]
        person = first['people'][0]
        person['name'] = prefix + 'Dương Minh Tuấn'
        person['aliases'] = []
        first.update(id=prefix + 'repeat-person', people=[person], substances=[])
        graph.add_news_case(first, news['news-100260920221957595'])
        edges = graph.run('MATCH (p:Person {name:$name})-[r:CHARGED_WITH]->() '
                          'RETURN p.aliases AS aliases,r.case_id AS case_id', name=person['name'])
        assert len(edges) == 2 and len({r['case_id'] for r in edges}) == 2
        assert all('Hoàng Nato' in r['aliases'] for r in edges)
        graph.run('MATCH (k:Case {id:$id}) DETACH DELETE k', id=first['id'])
        graph.run('MATCH ()-[r:CHARGED_WITH {case_id:$id}]->() DELETE r', id=first['id'])
        evidence = check_graph(graph)
        evidence['verification_mode'] = 'Manual source fixtures; no embeddings, LLM, judge, or benchmark scores.'
        evidence['sources'] = [doc_id for doc_id, _ in fixtures]
        Path('report/evidence/neo4j_fixtures.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        store = EmbeddingStore('verification')
        doc = news['news-100260918080821054']
        store.add_documents([Document('fixture-chunk', 'Lê Minh Thành bị tuyên 36 tháng tù.', {'doc_id':doc.id})])
        prompt = GraphRAGAgent(store, graph, lambda p: p).answer('Lê Minh Thành bị xử theo Điều nào?', top_k=1)
        assert 'Điều 251' in prompt and '36 tháng tù' in prompt
        print('Neo4j integration assertions passed: scoped crimes, aliases, mass threshold, aggregation, prompt.')
    finally:
        graph.run('MATCH (k:Case) WHERE k.id STARTS WITH $prefix DETACH DELETE k', prefix=prefix)
        graph.run('MATCH (p:Person) WHERE p.name IN $people DETACH DELETE p', people=created_people)
        graph.close()


if __name__ == '__main__':
    run()
