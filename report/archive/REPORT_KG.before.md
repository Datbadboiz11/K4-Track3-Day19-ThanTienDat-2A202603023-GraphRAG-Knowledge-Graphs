# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Thân Tiến Đạt  **MSSV:** 2A202603023  **Ngày:** 2026-10-05

> Kỳ vọng và thang điểm: `SUBMISSION.md`. Mọi số liệu phải khớp với `ket_qua_benchmark_kg.txt`. Bản thiết kế ontology nộp riêng ở `report/ONTOLOGY.md`.

## 1. Chi phí (10 điểm)

Dán 2 bảng `Indexing` và `Querying` từ `ket_qua_benchmark_kg.txt`:

```
== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176     56072        0   0.00112     56.4
graph       196     91958     4537   0.00923    134.9

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.43   1.00      694       47   0.00013     1.57
graph       0.69   1.33     3721       68   0.00059     2.43
```

| Chỉ số | Flat | Graph | Graph / Flat |
| --- | --- | --- | --- |
| Indexing USD | $0.00112 | $0.00923 | ×8.24 |
| Indexing giây | 56.4s | 134.9s | ×2.39 |
| Mỗi câu: USD | $0.00013 | $0.00059 | ×4.54 |
| Mỗi câu: giây | 1.57s | 2.43s | ×1.55 |
| Mỗi câu: in_tok | 694 | 3721 | ×5.36 |

**Chi phí tăng thêm đến từ đâu?** (2–3 câu)
> - Ở pha **Indexing**, chi phí tăng gấp ~8.24 lần (từ $0.00112 lên $0.00923) chủ yếu do GraphRAG phải gọi LLM trích xuất cấu trúc thực thể JSON từ 20 bài báo tin tức (tiêu tốn hơn 91.000 input tokens và 4.537 output tokens), trong khi Flat RAG chỉ dùng API embedding với đơn giá rất rẻ.
> - Ở pha **Querying**, chi phí mỗi câu tăng ~4.54 lần và input tokens tăng ~5.36 lần (từ 694 lên 3.721 tokens) do prompt của GraphRAG phải gánh thêm toàn bộ các facts trích xuất đa chặng từ đồ thị tri thức để cung cấp ngữ cảnh đầy đủ cho LLM.

## 2. Từng câu hỏi (10 điểm)

| Câu | Loại | Flat recall / judge | Graph recall / judge | Thắng | Vì sao (1 câu) |
| --- | --- | --- | --- | --- | --- |
| Q1 | single-hop-law | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai đều lấy được định nghĩa tiền chất trong Luật Phòng chống ma túy 2021 qua vector search cục bộ. |
| Q2 | single-hop-news | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai pipeline đều tìm được đoạn văn bản xử án tử hình của Trần Thanh Tuấn và Trần Minh Tâm trong cùng bài báo. |
| Q3 | cross-kb | 0.00 / 0 | 1.00 / 2 | Graph | Flat RAG trả về "Không đủ thông tin" do dữ liệu phân mảnh ở 2 KB, trong khi GraphRAG nối thành công bị cáo $\rightarrow$ Tội danh $\rightarrow$ Điều 251 khoản 1 (02-07 năm tù). |
| Q4 | cross-kb | 0.00 / 0 | 0.00 / 0 | Hòa | Cả hai đều trả về "Không đủ thông tin" do biệt danh 'Hoàng Nato' không được kích hoạt thành seed node trong tin tức đã crawl. |
| Q5 | cross-kb-multi-hop | 0.60 / 1 | 0.80 / 1 | Graph | GraphRAG lọc đúng khoản 4 Điều 250 (hơn 9.6kg MDMA chịu mức án 20 năm, chung thân hoặc tử hình), trong khi Flat RAG nhầm lẫn sang "khoản b". |
| Q6 | aggregation | 0.00 / 1 | 0.33 / 1 | Graph | GraphRAG duyệt toàn bộ cạnh `[:INVOLVES]` trên đồ thị và tìm đủ 4 vụ án liên quan đến MDMA, trong khi Flat RAG chỉ lấy 3 chunks rời rạc. |

## 3. Phân tích lỗi (20 điểm)

### Lỗi E1: Cầu nối gãy / Thiếu thực thể biệt danh (Trường hợp Q4 'Hoàng Nato')

- **Hiện tượng:** Cả Flat RAG và GraphRAG đều trả về "Không đủ thông tin" ở câu Q4 dù câu hỏi có trong bộ dữ liệu kiểm thử.
- **Bằng chứng:** 
Trích câu trả lời từ `ket_qua_benchmark_kg.txt`:
```
--- Q4 [cross-kb] flat recall=0.00 judge=0 1.23s
Không đủ thông tin.
--- Q4 [cross-kb] graph recall=0.00 judge=0 1.16s
Không đủ thông tin.
```

Truy vấn kiểm tra trong Neo4j Browser:
```cypher
MATCH (p:Person)
WHERE toLower(p.name) CONTAINS 'nato'
   OR any(a IN coalesce(p.aliases, []) WHERE toLower(a) CONTAINS 'nato')
RETURN p.name, p.aliases;
```

Kết quả:
```
(no changes, no records)
```

- **Nguyên nhân:** Trong khâu trích xuất tin tức bằng LLM (`extract_news_cases`), LLM đã không trích xuất biệt danh "Hoàng Nato" vào trường `aliases` của thực thể `Person` (hoặc đối tượng Dương Minh Tuấn không được gắn bí danh), khiến truy vấn `seed_facts` dựa trên tên trong câu hỏi không tìm thấy seed node nào, dẫn đến cầu nối sang luật bị đứt hoàn toàn.
- **Đề xuất sửa:** Bổ sung hướng dẫn nghiêm ngặt trong `NEWS_EXTRACTION_PROMPT` yêu cầu trích xuất toàn bộ biệt danh trong ngoặc kép hoặc ngoặc đơn vào mảng `aliases`. Đồng thời tại `seed_facts`, cho phép tìm kiếm mờ hoặc tìm kiếm trên cả thuộc tính `summary` của `Case`. Đánh đổi: Tăng nhẹ token của prompt trích xuất và có thể xuất hiện seed node nhiễu nếu tên quá ngắn.

---

### Lỗi E4: Phép đo sai / Mâu thuẫn giữa Recall và Judge (Trường hợp Q6)

- **Hiện tượng:** Ở câu Q6 (câu hỏi gom nhóm aggregation), GraphRAG liệt kê chính xác và đầy đủ 4 vụ án liên quan đến MDMA (trong đó có vụ vận chuyển hơn 9.6kg MDMA của Cái Quang Huy và vụ tại Viện Pháp y tâm thần Trung ương), được LLM Judge chấm đúng bản chất (Judge = 1/2), nhưng chỉ số `recall` từ khóa bắt buộc chỉ đạt 0.33.
- **Bằng chứng:** 
Trích nguyên văn câu trả lời của GraphRAG trong `ket_qua_benchmark_kg.txt`:
```
--- Q6 [aggregation] graph recall=0.33 judge=1 2.86s
Các vụ việc trong tin tức có liên quan đến ma túy MDMA bao gồm:
1. Vụ tổ chức sử dụng ma túy tại Sầm Sơn - liên quan đến 0,686g MDMA.
2. Vụ án tại Viện Pháp y tâm thần Trung ương - liên quan đến MDMA.
3. Vụ góp tiền mua ma túy tại Hà Nội - liên quan đến MDMA.
4. Vụ vận chuyển ma túy từ Đức về Việt Nam - liên quan đến tổng khối lượng hơn 9,6kg MDMA.
```

So sánh với `must_include` trong `data/benchmark_kg.json`:
```json
"must_include": ["Cái Quang Huy", "Lê Minh Thành", "Pháp y tâm thần"]
```

- **Nguyên nhân:** Mô hình GraphRAG trả lời theo phong cách tổng quan, gọi tên vụ án theo địa bàn / hành vi ("Vụ vận chuyển ma túy từ Đức về Việt Nam") thay vì nêu đích danh họ tên bị can ("Cái Quang Huy"). Vì hàm tính `recall` chỉ dùng so khớp chuỗi con chính xác (`keyword.lower() in answer.lower()`), nó đánh trượt 2 từ khóa "Cái Quang Huy" và "Lê Minh Thành", dẫn đến điểm recall bị kéo tụt xuống 0.33 dù câu trả lời hoàn toàn đúng thực tế.
- **Đề xuất sửa:** 
  1. Về phía Prompt: Bổ sung chỉ dẫn trong `GRAPH_PROMPT` yêu cầu: *"Khi liệt kê các vụ việc, bắt buộc nêu rõ họ tên các đối tượng/bị can chính liên quan nếu có"*.
  2. Về phía Metric: Không nên chỉ dựa vào exact substring match cho các câu hỏi tổng hợp, mà cần bổ sung các từ khóa thay thế tương đương (alias keywords) hoặc tin cậy vào điểm LLM Judge có rubric chấm theo ngữ nghĩa.

## 4. Kết luận (5 điểm)

Khi nào nên dùng KG, khi nào Flat RAG là đủ? Dẫn số liệu ở mục 1–2.
> - **Nên dùng Knowledge Graph (GraphRAG) khi:** Dữ liệu mang tính đa nguồn, phân mảnh cao và bài toán đòi hỏi suy luận logic xuyên văn bản (cross-KB / multi-hop). Minh chứng cụ thể ở câu Q3, Flat RAG hoàn toàn thất bại (Recall 0.00, Judge 0) vì không thể liên kết giữa tin tức và điều luật, trong khi GraphRAG đạt độ chính xác tuyệt đối (Recall 1.00, Judge 2). Nhìn chung trên toàn bộ bài test, GraphRAG nâng Recall trung bình từ **0.43 lên 0.69** và điểm Judge từ **1.00 lên 1.33**.
> - **Flat RAG là đủ khi:** Các câu hỏi chỉ mang tính tra cứu thông tin cục bộ (single-hop) nằm gọn trong một văn bản (như Q1 và Q2, cả hai bên đều đạt điểm tối đa Recall 1.00, Judge 2). Ở kịch bản này, Flat RAG vượt trội hoàn toàn về mặt kinh tế và hiệu năng: tiết kiệm hơn **8.24 lần** chi phí dựng hệ thống, rẻ hơn **4.54 lần** và nhanh hơn **1.55 lần** trên mỗi lượt truy vấn.

## 5. Tự kiểm (5 điểm)

```
$ pytest tests/ -q
................................................ [100%]
48 passed in 0.28s

$ python bench_kg.py --check
[OK] Dữ liệu: 18 điều luật, 20 bài báo
[OK] KG-1 link_entity
[OK] Neo4j kết nối được
[provider] chat = openai:gpt-4o-mini | embedding = openai:text-embedding-3-small
[OK] KG-2 build_graph: 148 node / 298 cạnh, đường xuyên 2 KB dài 2 cạnh
[OK] KG-3 context: 23 dữ kiện, có Điều 251
[OK] KG-4 GraphRAGAgent.answer
[OK] Chi phí check: 1 lần gọi LLM, $0.00078. Graph nhỏ (luật + 1 bài) vẫn còn trong Neo4j để bạn xem; chạy --judge để dựng graph đầy đủ.
```

Ảnh Neo4j: `report/img/kg_count.png`, `report/img/kg_cross_kb.png`, `report/img/kg_my_case.png`.
Người đã chọn cho `kg_my_case.png`: Trần Thanh Tuấn (vụ án mua bán hơn 36kg ma túy tại TP.HCM).

## Vấn đề gặp phải (không tính điểm)

Lỗi chưa giải quyết được: Không có. Hệ thống đã vượt qua toàn bộ 48 unit tests và kiểm tra hợp đồng tự động, benchmark chạy thành công và khớp số liệu 100%.
