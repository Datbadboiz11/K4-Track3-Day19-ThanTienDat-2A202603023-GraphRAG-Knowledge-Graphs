# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Thân Tiến Đạt  **MSSV:** 2A202603023  **Ngày:** 2026-10-05

> Kỳ vọng và thang điểm: `SUBMISSION.md`. Mọi số liệu dưới đây khớp 100% với `ket_qua_benchmark_kg.txt` sinh ra từ bản code cải tiến. Bản thiết kế ontology nộp ở `report/ONTOLOGY.md`. Bản kết quả đối chứng của ontology gợi ý nộp tại `ket_qua_benchmark_kg.hint.txt`.

## 1. Chi phí (10 điểm)

Dán 2 bảng `Indexing` và `Querying` từ `ket_qua_benchmark_kg.txt`:

```
== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176     56072        0   0.00112     65.4
graph       196     96298     5462   0.01043    204.0

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.43   1.00      694       47   0.00013     4.13
graph       1.00   2.00     1753      177   0.00036     5.43
```

| Chỉ số | Flat | Graph | Graph / Flat |
| --- | --- | --- | --- |
| Indexing USD | $0.00112 | $0.01043 | ×9.31 |
| Indexing giây | 65.4s | 204.0s | ×3.12 |
| Mỗi câu: USD | $0.00013 | $0.00036 | ×2.77 |
| Mỗi câu: giây | 4.13s | 5.43s | ×1.31 |
| Mỗi câu: in_tok | 694 | 1,753 | ×2.53 |

**Chi phí tăng thêm đến từ đâu?** (2–3 câu)
> - Ở pha **Indexing**, chi phí tăng gấp ~9.31 lần (từ $0.00112 lên $0.01043) chủ yếu do GraphRAG phải gọi LLM trích xuất cấu trúc thực thể JSON từ 20 bài báo tin tức (tiêu tốn hơn 96.000 input tokens và 5.462 output tokens), trong khi Flat RAG chỉ dùng API embedding với đơn giá rất rẻ.
> - Ở pha **Querying**, chi phí mỗi câu tăng ~2.77 lần và input tokens tăng ~2.53 lần (từ 694 lên 1.753 tokens) do prompt của GraphRAG được bổ sung các facts chắt lọc từ đồ thị tri thức (`bounded_facts` giới hạn 9.000 ký tự) để cung cấp ngữ cảnh định lượng và pháp lý đầy đủ cho LLM. So với bản gợi ý (3.721 tokens), bản cải tiến này đã tối ưu giảm hơn 52% số token ngữ cảnh dư thừa.

## 2. Từng câu hỏi (10 điểm)

| Câu | Loại | Flat recall / judge | Graph recall / judge | Thắng | Vì sao (1 câu) |
| --- | --- | --- | --- | --- | --- |
| Q1 | single-hop-law | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai pipeline đều lấy được định nghĩa tiền chất trong Luật Phòng chống ma túy 2021 qua vector search cục bộ. |
| Q2 | single-hop-news | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai pipeline đều tìm được đoạn văn bản xử án tử hình của Trần Thanh Tuấn và Trần Minh Tâm trong bài báo. |
| Q3 | cross-kb | 0.00 / 0 | 1.00 / 2 | Graph | Flat RAG trả về "Không đủ thông tin" do dữ liệu phân mảnh ở 2 KB, trong khi GraphRAG nối thành công bị cáo $\rightarrow$ Tội danh $\rightarrow$ Điều 251 khoản 1 (02-07 năm tù). |
| Q4 | cross-kb | 0.00 / 0 | 1.00 / 2 | Graph | Flat RAG thất bại hoàn toàn, trong khi GraphRAG bắt chính xác biệt danh 'Hoàng Nato' (Dương Minh Tuấn) và dùng hàm `severity` tìm đúng khung tối đa 20 năm/chung thân theo Điều 255 khoản 4 BLHS. |
| Q5 | cross-kb-multi-hop | 0.60 / 1 | 1.00 / 2 | Graph | GraphRAG vượt trội nhờ logic đối chiếu số học `9.600g > 100g` để chỉ đích danh Khoản 4 Điều 250 (tù 20 năm, chung thân hoặc tử hình), trong khi Flat RAG nhầm lẫn sang "khoản b". |
| Q6 | aggregation | 0.00 / 1 | 1.00 / 2 | Graph | GraphRAG bắt trọn vẹn cả 3 thực thể bắt buộc ("Cái Quang Huy", "Lê Minh Thành", "Pháp y tâm thần") nhờ prompt yêu cầu nêu rõ họ tên đối tượng và nguồn tin, đạt điểm tuyệt đối 2/2. |

## 3. Phân tích lỗi (20 điểm)

### Lỗi E1 / E2: Flat RAG gãy cầu nối và thiếu ngữ cảnh luật ở câu hỏi liên kết chéo (Q3 & Q4)

- **Hiện tượng:** Flat RAG hoàn toàn thất bại ở các câu hỏi cross-KB như Q3 và Q4, trả về *"Không đủ thông tin"* dù trong 2 cơ sở dữ liệu có đầy đủ dữ kiện.
- **Bằng chứng:** 
Trích câu trả lời của Flat RAG trong `ket_qua_benchmark_kg.txt`:
```
--- Q3 [cross-kb] flat recall=0.00 judge=0 3.80s
Không đủ thông tin.
--- Q4 [cross-kb] flat recall=0.00 judge=0 2.16s
Không đủ thông tin.
```
Trong khi GraphRAG trả lời chính xác:
```
--- Q4 [cross-kb] graph recall=1.00 judge=2 4.58s
Giang hồ 'Hoàng Nato' (Dương Minh Tuấn) bị bắt về hành vi tổ chức sử dụng trái phép chất ma túy. Hành vi này có thể bị phạt tù tối đa lên đến 20 năm hoặc tù chung thân theo Điều 255, khoản 4 Bộ luật Hình sự. [Nguồn news-100260920221957595]
```

- **Nguyên nhân:** Flat RAG chỉ dựa trên độ tương đồng vector của từng chunk độc lập. Tên đối tượng và hành vi phạm tội nằm ở KB tin tức, còn tên Điều luật và khung hình phạt nằm ở KB luật. Không có bất kỳ đoạn văn bản (chunk) nào chứa đồng thời cả hai thông tin này. Do không có đồ thị tri thức để bắc cầu suy luận đa chặng (`Person -> Case -> Crime -> Article -> Clause`), Flat RAG không thể tìm thấy dữ liệu liên quan.
- **Đề xuất sửa:** Xây dựng Knowledge Graph liên kết qua node thực thể cầu nối `Crime` (tội danh) và `Substance` (chất ma túy), kết hợp trích xuất bí danh đối tượng (`tức 'Hoàng Nato'`) như đã hiện thực thành công trong đồ thị mới.

---

### Lỗi E3: Xung đột ghi đè thuộc tính khi cùng một sự kiện được đưa tin bởi nhiều bài báo (Cross-source Property Overwrite)

- **Hiện tượng:** Trong KB tin tức, có nhiều bài báo cùng đưa tin về một chuyên án lớn (ví dụ vụ Cái Quang Huy vận chuyển ma túy từ Đức về Nội Bài, hay vụ chuyên án triệt phá đường dây của Hoàng Nato với 126 đối tượng). Các bài báo khác nhau ghi nhận khối lượng tang vật ở các thời điểm khác nhau (bài ghi khối lượng 1 lần vận chuyển, bài ghi tổng khối lượng cả chuyên án).
- **Bằng chứng:** 
Truy vấn kiểm tra các bản ghi của cùng một chất trong vụ án:
```cypher
MATCH (k:Case)-[r:INVOLVES]->(s:Substance {name: 'MDMA'})
RETURN k.name, r.amount, r.amount_g;
```
Nếu áp dụng cơ chế `MERGE` thông thường mà không có chiến lược xử lý xung đột, bài báo đọc sau sẽ ghi đè thuộc tính `r.amount` của bài báo đọc trước, làm mất đi tính toàn vẹn của tang vật.
- **Nguyên nhân:** LLM trích xuất tin tức độc lập từng bài báo. Thuộc tính trên quan hệ trong Neo4j nếu chỉ gán `SET r.amount = s.amount` sẽ tự động ghi đè giá trị cũ bằng giá trị mới của bài báo cuối cùng được duyệt.
- **Đề xuất sửa:** 
  1. Bảo toàn lịch sử quan sát bằng cách nối chuỗi khi có sự khác biệt (`amount = merged[name]["amount"] + "; " + amount`).
  2. Định danh duy nhất cho từng vụ việc bằng mã hash SHA256 (`case_id = doc.id + ":" + hash(name)`), đồng thời gán phạm vi vụ án lên quan hệ tội danh của bị can: `(:Person)-[:CHARGED_WITH {case_id}]->(:Crime)`.

## 4. Kết luận (5 điểm)

Khi nào nên dùng KG, khi nào Flat RAG là đủ? Dẫn số liệu ở mục 1–2.
> - **Nên dùng Knowledge Graph (GraphRAG) khi:** Dữ liệu mang tính đa nguồn, phân mảnh cao và bài toán đòi hỏi suy luận logic, đối chiếu số học định lượng xuyên văn bản (cross-KB / multi-hop). Minh chứng rõ nét nhất: GraphRAG đạt độ chính xác tuyệt đối **Recall = 1.00 (100%)** và **Judge = 2.00 / 2.00** trên toàn bộ 6 câu hỏi kiểm thử (vượt trội hoàn toàn so với Flat RAG chỉ đạt Recall 0.43, Judge 1.00). Ở các câu hỏi phức tạp (Q3, Q4, Q5, Q6), GraphRAG chiến thắng 100%.
> - **Flat RAG là đủ khi:** Các câu hỏi chỉ mang tính tra cứu thông tin cục bộ (single-hop) nằm gọn trong một văn bản (như Q1 và Q2, cả hai bên đều đạt điểm tối đa Recall 1.00, Judge 2). Ở kịch bản này, Flat RAG tiết kiệm hơn **9.31 lần** chi phí indexing và nhanh hơn về độ trễ, hoàn toàn không cần đầu tư thêm độ phức tạp của đồ thị.

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
[OK] KG-3 context: 2 dữ kiện, có Điều 251
[OK] KG-4 GraphRAGAgent.answer
[OK] Chi phí check: 1 lần gọi LLM, $0.00089. Graph nhỏ (luật + 1 bài) vẫn còn trong Neo4j để bạn xem; chạy --judge để dựng graph đầy đủ.
```

Ảnh Neo4j: `report/img/kg_count.png`, `report/img/kg_cross_kb.png`, `report/img/kg_my_case.png`.
Người đã chọn cho `kg_my_case.png`: Trần Thanh Tuấn (vụ án mua bán hơn 36kg ma túy tại TP.HCM).

## Vấn đề gặp phải (không tính điểm)

Lỗi chưa giải quyết được: Không có. Hệ thống đã đạt điểm số hoàn hảo 100% Recall và 2.0/2.0 Judge trên tất cả các câu hỏi kiểm thử.
