"""Question-scoped Cypher retrieval; shared substances do not seed individual cases."""

from __future__ import annotations

import json
import re

from .graph_rules import bounded_facts, clean_name, find_substances, matching_threshold, parse_amount


def context(graph, question: str, doc_ids: list[str], max_facts: int = 60, max_chars: int = 9000) -> list[str]:
    q = clean_name(question)
    substances = find_substances(question)
    aggregation = bool(substances and re.search(r"những vụ|các vụ|liệt kê|tất cả|bao nhiêu vụ", q))
    wants_max = bool(re.search(r"tối đa|cao nhất|nặng nhất", q))
    wants_mass = bool(re.search(r"khối lượng|định lượng|khoản nào|khoản.*áp dụng", q))
    people = graph.run(
        """MATCH (p:Person)
        WHERE toLower($q) CONTAINS toLower(p.name)
           OR any(a IN coalesce(p.aliases, []) WHERE size(a) >= 3 AND toLower($q) CONTAINS toLower(a))
        RETURN p.name AS name ORDER BY size(p.name) DESC, p.name""", q=q)
    names = [p['name'] for p in people]
    case_rows = graph.run(
        """MATCH (k:Case)
        WHERE CASE
          WHEN $aggregation THEN EXISTS { MATCH (k)-[:INVOLVES]->(s:Substance) WHERE s.name IN $substances }
          WHEN size($names) > 0 THEN EXISTS { MATCH (p:Person)-[:INVOLVED_IN]->(k) WHERE p.name IN $names }
          ELSE k.doc_id IN $doc_ids END
        OPTIONAL MATCH (p:Person)-[r:INVOLVED_IN]->(k)
        WITH k, collect(DISTINCT {name:p.name, role:r.role, charge:r.charge, sentence:r.sentence,
                                substances_json:r.substances_json}) AS people
        OPTIONAL MATCH (k)-[sr:INVOLVES]->(s:Substance)
        RETURN k.id AS id, k.name AS name, k.summary AS summary, k.doc_id AS doc_id,
               people, collect(DISTINCT {name:s.name, amount:sr.amount}) AS substances
        ORDER BY k.doc_id, k.name""",
        aggregation=aggregation, substances=substances, names=names, doc_ids=doc_ids)
    facts = []
    for case in case_rows:
        persons = [p for p in case['people'] if p['name'] and (aggregation or not names or p['name'] in names)]
        details = '; '.join(f"{p['name']}: {p.get('charge') or 'chưa rõ tội danh'}, mức án: {p.get('sentence') or 'chưa có'}"
                            for p in persons)
        material = '; '.join(f"{s['name']}: {s.get('amount') or 'không nêu khối lượng'}"
                             for s in case['substances'] if s['name'] and (not aggregation or s['name'] in substances))
        facts.append(f"[Nguồn {case['doc_id']}] Vụ '{case['name']}'. Người: {details}. Tang vật: {material}.")
    # A substance aggregation needs news facts, not unrelated legal articles.
    if aggregation:
        return bounded_facts(facts, max_facts, max_chars)

    crimes = graph.run(
        """MATCH (p:Person)-[r:CHARGED_WITH]->(c:Crime)
        WHERE p.name IN $names AND r.case_id IN $case_ids
        RETURN DISTINCT c.name AS name ORDER BY name""",
        names=names, case_ids=[k['id'] for k in case_rows]) if names else []
    if not crimes:
        # Prefer the person's charge on the case edge; never borrow another defendant's crime.
        linked = [p['charge'] for k in case_rows for p in k['people']
                  if p.get('charge') and (not names or p['name'] in names)]
        if linked:
            crimes = [{'name': c} for c in sorted(set(linked))]
        elif not names:
            crimes = graph.run(
                """MATCH (k:Case)-[:CHARGED_WITH]->(c:Crime)
                WHERE k.id IN $case_ids RETURN DISTINCT c.name AS name ORDER BY name""",
                case_ids=[k['id'] for k in case_rows])
    article_nums = re.findall(r"điều\s+(\d+)\b", q)
    law_rows = graph.run(
        """MATCH (a:Article)-[:HAS_CLAUSE]->(cl:Clause)
        WHERE a.doc_id IN $law_docs
           OR any(num IN $numbers WHERE a.id = 'Điều ' + num + ' BLHS' OR a.id = 'Điều ' + num + ' Luật PCMT')
           OR EXISTS { MATCH (a)-[:DEFINES]->(c:Crime) WHERE c.name IN $crimes }
        RETURN a.id AS article_id, a.doc_id AS doc_id, a.title AS title, cl.number AS number,
               cl.penalty AS penalty, cl.text AS text, cl.thresholds_json AS thresholds_json
        ORDER BY a.id, cl.number""",
        law_docs=[] if names or article_nums else [d for d in doc_ids if d.startswith(('blhs-', 'pcmt-'))],
        numbers=article_nums, crimes=[] if article_nums else [c['name'] for c in crimes])
    by_article = {}
    for row in law_rows:
        by_article.setdefault(row['article_id'], []).append(row)
    personal = [s for k in case_rows for p in k['people'] if p['name'] in names
                for s in json.loads(p.get('substances_json') or '[]')]
    observations = [s for s in (personal or [s for k in case_rows for s in k['substances']])
                    if s['name'] and (not substances or s['name'] in substances)]
    for article, clauses in by_article.items():
        if wants_max:
            punishments = [r for r in clauses if r.get('penalty') and
                           re.search(r'phạt tù|tù chung thân|tử hình', r['penalty'])]
            # Select imprisonment clauses by their actual sanction, not by the largest clause number.
            def severity(row):
                p = row['penalty']
                years = [int(n) for n in re.findall(r'(\d+)\s*năm', p)]
                return (3 if 'tử hình' in p else 2 if 'chung thân' in p else 1, max(years, default=0))
            selected = [max(punishments, key=severity)] if punishments else []
        elif wants_mass:
            selected = []
            for row in clauses:
                for s in observations:
                    rule = matching_threshold(row, s)
                    if rule:
                        amount = parse_amount(s['amount'])
                        facts.append(f"[Nguồn {row['doc_id']}] Đối chiếu {s['name']} {s['amount']} "
                                     f"= {'hơn ' if amount['qualifier']=='gt' else ''}{amount['grams']:g} gam "
                                     f"với ngưỡng {rule['min_g']:g} gam: khoản {row['number']} {article}. "
                                     f"Điều kiện: {rule['evidence']}. Khung: {row['penalty']}.")
                        selected.append(row)
            if not selected:
                # Unknown mass: show conditions without claiming a clause is applicable.
                selected = [r for r in clauses if any(s in r['text'] for s in substances)]
        elif names or crimes:
            selected = [r for r in clauses if r['number'] == 1]
        else:
            selected = clauses  # Definitions/explicit law requests, with the overall budget below.
        seen = set()
        for row in selected:
            if row['number'] in seen:
                continue
            seen.add(row['number'])
            if row.get('penalty') and (names or crimes or wants_max or wants_mass):
                excerpt = row['penalty']
            else:
                excerpt = row['text']
            facts.append(f"[Nguồn {row['doc_id']}; {article} - {row['title']}] khoản {row['number']}: {excerpt}")
    return bounded_facts(facts, max_facts, max_chars)
