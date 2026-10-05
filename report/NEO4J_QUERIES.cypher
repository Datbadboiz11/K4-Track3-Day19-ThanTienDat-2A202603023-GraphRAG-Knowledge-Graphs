// Chạy từng khối riêng trong Neo4j Browser sau benchmark đầy đủ.
// Gõ :clear trước mỗi khối. Chụp nguyên cửa sổ, thấy query và Results overview.

// 1. report/img/kg_count.png
MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

// 2. report/img/kg_cross_kb.png (khớp tội danh của từng người trong vụ)
MATCH path=(p:Person)-[r:INVOLVED_IN]->(k:Case)-[:CHARGED_WITH]->(c:Crime)<-[:DEFINES]-(a:Article)
WHERE r.charge = c.name
RETURN path LIMIT 25;

// 3. report/img/kg_my_case.png; người tự chọn: Trần Thanh Tuấn
MATCH path=(p:Person {name:'Trần Thanh Tuấn'})-[:INVOLVED_IN]->(k:Case)-[:CHARGED_WITH]->(c:Crime)<-[:DEFINES]-(a:Article)
MATCH (p)-[charge:CHARGED_WITH]->(c) WHERE charge.case_id = k.id
OPTIONAL MATCH material=(k)-[:INVOLVES|LOCATED_IN]->()
RETURN path, material;

// E1: kiểm tra biệt danh, không suy nguyên nhân từ một câu trả lời thiếu thông tin
MATCH (p:Person)
WHERE any(alias IN coalesce(p.aliases,[]) WHERE toLower(alias) CONTAINS 'nato')
RETURN p.name, p.aliases;

// Kiểm tra tội danh riêng và giữ provenance theo vụ
MATCH (p:Person {name:'Cái Quang Huy'})-[r:CHARGED_WITH]->(c:Crime)<-[:DEFINES]-(a:Article)
RETURN p.name, r.case_id, r.doc_id, c.name, a.id;

// Kiểm tra điều kiện định lượng đã trích từ nguồn luật
MATCH (a:Article {id:'Điều 250 BLHS'})-[:HAS_CLAUSE]->(cl:Clause)
RETURN cl.number, cl.penalty, cl.thresholds_json ORDER BY cl.number;

// Q6: liệt kê theo source; nhiều bài có thể tường thuật cùng sự kiện
MATCH (k:Case)-[r:INVOLVES]->(:Substance {name:'MDMA'})
OPTIONAL MATCH (p:Person)-[:INVOLVED_IN]->(k)
RETURN k.doc_id, k.name, r.amount, collect(DISTINCT p.name) AS people
ORDER BY k.doc_id, k.name;
