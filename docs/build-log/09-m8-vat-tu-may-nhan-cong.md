# M8 — Vật tư, máy, nhân công

## 1. Mục tiêu

Theo kế hoạch (prompt 4.5):
- kho công trường;
- đề xuất vật tư theo công tác → (mua hàng) → cấp phát theo công tác → hoàn trả, hao hụt;
- so định mức với thực tế, cảnh báo vượt định mức;
- máy thi công: điều chuyển (máy sở hữu kèm Asset Movement), ca máy, bảo dưỡng;
- tổ đội, công nhân, chấm công theo công tác;
- chi phí thực tế so với dự toán;
- phân quyền theo dự án trên DocType kho và mua hàng của ERPNext.

Tiêu chí hoàn thành: kỹ sư đề xuất trên điện thoại → thủ kho cấp phát → báo cáo định mức so với thực tế đúng.

## 2. Lõi: phạm vi dự án trên kho và mua hàng của ERPNext

| DocType của ERPNext | Cột dự án | Ghi chú |
|---|---|---|
| Warehouse | `pm_project` (mới) | Kho công trường của dự án |
| Location | `pm_project` (mới) | Vị trí công trường (nơi đặt tài sản) |
| Material Request | `pm_project` (mới) | Chép xuống `project` của từng dòng; thêm `pm_client_uuid` (gửi lại không trùng) |
| Stock Entry | `project` (sẵn có) | |
| Asset Movement | `pm_project` (mới) | |
| Purchase Order, Purchase Receipt, Purchase Invoice | `project` (sẵn có) | `finance.view_all` cũng xem hết |

`permissions.stock_query` và `has_stock_permission` áp cho các DocType trên (`constants.STOCK_SCOPED`):
- nhân viên của hệ thống chỉ thấy phiếu, kho của dự án mình được xem;
- ghi cần quyền `stock.manage` (đề xuất: `material.request`) trong dự án của phiếu và trong dự án của **mọi kho** mà phiếu chạm tới. Vì vậy chuyển kho giữa hai dự án cần quyền ở cả hai; kho tổng không thuộc dự án nào;
- không bị thu hẹp: quản trị; người ngoài hệ thống (chỉ có vai trò ERPNext như kế toán dùng Desk) theo đúng quyền của ERPNext; người có quyền toàn cục mới `stock.cross_project` (kho tổng).

Quyền trong dự án mới:
- `material.request` (đề xuất vật tư): Quản lý dự án, Chỉ huy trưởng, Kỹ sư, Thủ kho;
- `stock.manage` (nhập, xuất, chuyển kho): Quản lý dự án, Chỉ huy trưởng, Thủ kho.

Thủ kho được gán sẵn vai trò ERPNext "Stock User"; Kế toán dự án được gán "Accounts User", "Purchase User". Các vai trò này được thêm khi thêm thành viên, nhờ bảng "vai trò cần có" của vai trò dự án (có từ M1). Site cài trước M8 được bổ sung qua patch `m8_stock_capabilities`.

Lõi thêm hook `pm_masters`: lớp ngành khai báo danh mục riêng, hiện trong màn danh mục chung. Mục 3 kể ba danh mục của lớp thi công.

## 3. Lớp thi công: DocType và trường mới

| DocType | Nội dung |
|---|---|
| PMC Material Norm (+PMC Norm Material) | Định mức vật tư theo mã hiệu: vật tư, hao phí cho một đơn vị công việc, % hao hụt. Danh mục "Định mức vật tư" |
| PMC Material Plan | Kế hoạch vật tư của từng công tác = khối lượng thiết kế × hao phí (gồm hao hụt). Tính lại khi duyệt BOQ hoặc khi bấm "Tính lại kế hoạch" |
| PMC Machine (+PMC Machine Maintenance) | Máy: sở hữu (gắn Asset của ERPNext) hoặc thuê; đơn giá ca, định mức nhiên liệu, đang ở dự án nào, ngày bảo dưỡng tiếp theo, lịch sử bảo dưỡng. Danh mục "Máy thi công" |
| PMC Machine Transfer | Lịch sử điều chuyển máy (từ dự án, đến dự án hoặc về công ty, phiếu điều chuyển tài sản) |
| PMC Machine Shift | Ca máy: máy, công tác, ngày, số ca, giờ, nhiên liệu, người vận hành, thành tiền |
| PMC Worker | Công nhân thời vụ (không phải người dùng hệ thống): tổ đội, nghề, đơn giá công; số CCCD ở permission level 1. Danh mục "Công nhân" |
| PMC Crew Attendance (+PMC Attendance Line) | Chấm công một tổ đội, một ngày: mỗi người, công tác, số công, giờ tăng ca. Nháp → Đã nộp → Đã xác nhận |

Tổ đội dùng PM Team của lõi, loại "Tổ đội".

Trường thêm vào DocType của ERPNext:
- `pmc_task` (công tác) trên dòng của Material Request, Purchase Order, Purchase Receipt, Purchase Invoice, Stock Entry. ERPNext tự chép trường cùng tên khi lập phiếu này từ phiếu kia;
- `pmc_kind` trên Stock Entry: Nhập kho, Cấp phát, Hoàn trả, Hao hụt, Điều chuyển;
- chi phí trên Task: vật tư, máy, nhân công, tổng. Các trường này ở permission level 1, nên Desk không hiện chúng cho người thường.

## 4. Luồng

**Vật tư** (`services/materials.py`, tab "Vật tư"):
1. Thủ kho (hoặc người lập kế hoạch) lập kho công trường một lần: kho "Kho {mã dự án}" thuộc nhóm "Kho công trường".
2. Kỹ sư **đề xuất** vật tư cho công tác trên điện thoại.
   - Đề xuất đi qua hàng đợi gửi lại nên viết được khi mất mạng.
   - Kết quả là một Material Request "Material Issue" của kho công trường, đã submit.
   - Thủ kho của dự án được báo.
3. Thủ kho **nhập kho** các đợt hàng về (kèm đơn giá), rồi **cấp phát** theo đề xuất: phiếu điền sẵn các dòng còn thiếu.
   - Dòng cấp phát gắn với dòng đề xuất, nên ERPNext tự chuyển đề xuất sang "Issued".
   - Người đề xuất được báo.
4. **Hoàn trả** phần chưa dùng, lấy theo giá lúc xuất (không trả quá số đã cấp). **Hao hụt** phải ghi lý do. **Điều chuyển** sang kho dự án khác.
   - Mỗi thao tác là một Stock Entry đã submit. Sổ kho, giá trị tồn và bút toán là của ERPNext.
   - Thiếu tồn thì báo "Không đủ tồn kho".
5. **Định mức so với thực tế**, theo từng công tác và vật tư:
   - các số: kế hoạch, đã đề xuất, đã cấp, trả lại, hao hụt;
   - **đã dùng** = cấp − trả;
   - **định mức của khối lượng đã làm** = hao phí × khối lượng đã làm (lấy từ nhật ký);
   - chênh lệch = đã dùng − định mức;
   - **vượt định mức** (đỏ, có cảnh báo "Vượt định mức vật tư"): đã dùng quá định mức của toàn bộ khối lượng thiết kế, hoặc công tác đã xong mà quá định mức của khối lượng đã làm, quá 5%;
   - **cấp trước khối lượng** (vàng, không cảnh báo): công tác chưa xong mà đã cấp nhiều hơn phần khối lượng đã làm cần; vật tư đang chờ ở mặt bằng.

Mua hàng (Purchase Order, Purchase Receipt) vẫn làm trong Desk của ERPNext. `pmc_task` đi theo các phiếu đó.

**Máy** (`services/machines.py`, tab "Máy"):
- người lập kế hoạch đưa máy rảnh vào dự án, hoặc trả về công ty;
- máy sở hữu có Asset: mỗi lần điều chuyển lập và submit một Asset Movement tới vị trí công trường (Location có `pm_project`) hoặc "Bãi máy công ty";
- kỹ sư ghi **ca máy** cho công tác trên điện thoại (được cả khi mất mạng): thành tiền = số ca × đơn giá ca lúc ghi; nhiên liệu được so với định mức (lít/ca);
- cảnh báo "Máy đến hạn bảo dưỡng" khi ngày bảo dưỡng tiếp theo trong 3 ngày tới hoặc đã qua.

**Nhân công** (`services/labour.py`, tab "Chấm công"):
- tổ trưởng mở bảng của tổ mình theo ngày, đã điền sẵn công nhân (1 công mỗi người);
- tổ trưởng chọn công tác, số công, giờ tăng ca rồi nộp (được cả khi mất mạng);
- chỉ huy trưởng xác nhận hoặc trả lại;
- đơn giá công chốt lúc lưu; công đã xác nhận × đơn giá là chi phí nhân công của công tác.

**Chi phí** (`services/costs.py`, tab "Chi phí", cần `finance.view`):
- chi phí thực tế của từng công tác:
  - vật tư (giá trị xuất trừ phần trả lại, cộng hao hụt);
  - máy;
  - nhân công;
- lưu trên Task, tính lại mỗi khi có phiếu kho, kể cả phiếu lập trong Desk (doc_events), ca máy hoặc bảng chấm công thay đổi;
- bảng chi phí cộng dồn theo cây, so với giá trị dự toán và **giá trị đã thi công** (khối lượng đã làm × đơn giá).

## 5. File chính

| File | Nội dung |
|---|---|
| Lõi `constants.py`, `setup/install.py`, `patches/m8_stock_capabilities.py` | Quyền mới, vai trò Frappe kèm theo, trường dự án trên kho và mua hàng |
| Lõi `permissions.py` (`stock_query`, `has_stock_permission`), `services/stock.py`, `extensions.py` (`masters`, `registry`) | Phạm vi kho và mua hàng; danh mục của lớp ngành |
| Lớp `services/materials.py`, `machines.py`, `labour.py`, `costs.py`, `api/site.py` | Nghiệp vụ và API |
| Lớp `setup/demo_site.py` | Dữ liệu mẫu công trường |
| Lớp `frontend/src/MaterialsTab.vue`, `MachinesTab.vue`, `LabourTab.vue`, `CostTab.vue` | Bốn tab mới; ba loại mục hàng đợi: đề xuất vật tư, ca máy, chấm công |
| `scripts/e2e/ui/site_flow.mjs`, `scripts/perf/materials_check.py` | Kịch bản trình duyệt, đo hiệu năng |

## 6. Quyết định kỹ thuật

- **Không có DocType "sử dụng vật tư" riêng:** kế hoạch dự kiến có PMC Material Usage. Số đã dùng của công tác được đọc thẳng từ các Stock Entry đã submit có `pmc_task`. Như vậy chỉ có một sổ, không có hai nơi phải khớp nhau.
- **Đề xuất là Material Request "Material Issue" của kho công trường**, không phải "Purchase". Kho chưa đủ hàng thì phòng mua hàng lập PO/PR trong Desk về kho công trường, rồi thủ kho mới cấp phát.
- **`pm_project` của Material Request không bắt buộc ở mức DocType**, vì phiếu tự đặt hàng lại (reorder) của ERPNext không có dự án. Các luồng của hệ thống luôn điền nó.
- **Hoàn trả theo giá lúc xuất,** để chi phí của công tác giảm đúng bằng phần đã tính. Phiếu nhận lại vào kho ghi nhận giá đó.
- **Phạm vi kho chỉ thu hẹp nhân viên của hệ thống.** Người chỉ có vai trò ERPNext (ví dụ kế toán làm việc trong Desk) giữ đúng quyền của ERPNext, để không vỡ quy trình kế toán sẵn có.
- **Thông báo lỗi quyền cụ thể:** dịch vụ dùng `frappe.throw(..., frappe.PermissionError)`, nên câu như "Vai trò của bạn trong dự án không xem được chi phí" hiện lên thay cho câu chung "Bạn không có quyền…".
- **Giờ tăng ca được ghi lại nhưng chưa tính tiền:** chưa có quy định đơn giá tăng ca của doanh nghiệp.

## 7. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **282 + 17** (trước M8: 277 + 17; thêm `test_stock_scope`, 5 bài: thủ kho dự án A không thấy kho, phiếu, đề xuất của dự án B, không thấy kho tổng; chuyển kho cần cả hai kho; người ngoài hệ thống và người có `stock.cross_project` không bị thu hẹp; hook phủ đủ) |
| `run-tests --app pm_construction` | **51/51** (trước M8: 27; thêm `test_materials`, 15 bài: kế hoạch theo định mức, kho, đề xuất → nhập → cấp phát → trả lại, ai làm gì, gửi lại không trùng, thiếu tồn, hao hụt, điều chuyển, phiếu lập trong Desk, cấp trước khối lượng và vượt định mức, cảnh báo, ai đọc gì; `test_machines_labour`, 9 bài: máy sở hữu kèm Asset Movement, máy thuê, ca máy, bảo dưỡng, chấm công từ nháp tới xác nhận, một bảng mỗi tổ mỗi ngày, các trường hợp bị từ chối, bảng chi phí) |
| vitest | **200/200** (16 tệp; thêm `site.layer.test.js`: đọc dòng phiếu, nhóm theo công tác, chấm công, gửi từ hàng đợi với đúng mã, tab Vật tư cấp phát từ đề xuất, tab Chi phí) |
| `scripts/e2e/ui/site_flow.mjs` | **32/32** trên Edge thật (mục 9) |
| Các kịch bản cũ | thí điểm M7 23/23 (trên dữ liệu mẫu đã thêm phần M8) |
| Hiệu năng | BOQ 3.000 công tác: 9.000 dòng kế hoạch vật tư trong 2,4–3,9 s; tổng quan định mức so với thực tế 0,55–0,88 s; phiếu cấp phát 99 dòng khoảng 4 s, phần lớn là ERPNext. Xem [HIEU_NANG.md](../HIEU_NANG.md#m8--vật-tư-trên-boq-3000-công-tác-2026-11-11) |

Lỗi tìm ra khi chạy test và kịch bản, đã sửa:
- **clean clone: tạo site mới hỏng.** Lớp thi công tạo nhóm "Vật tư xây dựng" ngay khi cài, lúc thiết lập ban đầu của ERPNext chưa chạy nên chưa có nhóm gốc "All Item Groups". Nay bước này đợi đến lần migrate sau khi thiết lập. Site dev không gặp vì đã có nhóm gốc từ trước;
- **clean clone: tên cây kho theo ngôn ngữ của site.** Trên site thứ hai chỉ có lõi, ERPNext đặt tên kho bằng tiếng Việt ("Tất cả Kho - CTXD", "Cửa hàng - CTXD") thay vì "All Warehouses", "Stores", nên test phạm vi kho hỏng. Mã của lớp thi công khi đó cũng sẽ không lập được kho công trường hay nhóm vật tư trên một site như vậy. Nay gốc cây kho, gốc nhóm vật tư và các tài khoản tài sản được tìm theo vị trí trong cây và loại tài khoản, không theo tên;
- ERPNext v16 bắt buộc "Net Purchase Amount" khi lập tài sản;
- điều chuyển máy báo "Máy đã ở đó" trước khi kiểm quyền;
- `pm_masters` khai báo đường dẫn hàm, trong khi lõi chỉ đọc dict;
- test của lớp ngành không tìm thấy `@vue/test-utils` (thêm vào dedupe của Vite);
- câu lỗi quyền không đến được giao diện (mục 6);
- **vật tư cấp trước khi báo khối lượng bị coi là vượt định mức.** Phép đo trên 3.000 công tác lộ ra lỗi này: công tác nào đã nhận vật tư mà chưa báo khối lượng đều bị báo. Ở công trường thật, vật tư được cấp ra mặt bằng trước khi làm, nên sẽ có rất nhiều cảnh báo nhầm. Quy tắc nay như sau:
  - **vượt định mức** (có cảnh báo): đã dùng quá định mức của toàn bộ khối lượng thiết kế, hoặc công tác đã xong mà đã dùng quá định mức của khối lượng đã làm;
  - **cấp trước khối lượng** (nhãn vàng, không cảnh báo): công tác chưa xong mà đã cấp quá phần khối lượng đã làm cần;
- dữ liệu thử còn sót trên site dev khi `setUpClass` hỏng giữa chừng (đã dọn; vật tư và định mức thử nay được xóa khi test xong).

## 8. Dữ liệu mẫu nhà xưởng (bổ sung)

- Thủ kho `demo.thukho@pm.localhost` (Đỗ Thủ Kho).
- 11 vật tư và 11 định mức theo các mã hiệu của BOQ mẫu (số liệu minh họa).
- Kho "Kho DEMO-XD01": nhập đợt 1; cấp phát cho các công tác phần móng và cột.
  - Xi măng của bê tông móng cấp nhiều hơn định mức khoảng 6%, nên có cảnh báo vượt định mức.
  - Có một lần trả lại 150 kg xi măng.
- Một đề xuất cốt thép cột của kỹ sư đang chờ cấp phát.
- Máy:
  - máy đào sở hữu (Asset của ERPNext, đã điều chuyển tới công trường, đến hạn bảo dưỡng sau 2 ngày, nên có cảnh báo);
  - máy trộn;
  - cần trục thuê;
  - kèm ca máy theo công tác.
- Hai tổ đội (tổ nề của Võ Tổ Trưởng, tổ sắt), 7 công nhân, chấm công 10 ngày; ngày gần nhất chờ chỉ huy trưởng xác nhận.

## 9. Tiêu chí hoàn thành

`site_flow.mjs` trên dữ liệu mẫu (ảnh trong `scripts/e2e/ui/out/site/`):
1. **Kỹ sư, trên điện thoại, mất mạng:**
   - đề xuất 600 kg xi măng cho công tác bê tông cột, và đề xuất được giữ lại;
   - có mạng lại thì đề xuất tự gửi và đến kho, gắn đúng công tác;
   - ghi một ca máy trộn;
   - trang không cuộn ngang.
2. **Thủ kho, trên máy tính:**
   - phiếu cấp phát điền sẵn 600 kg từ đề xuất; cấp phát xong thì đề xuất chuyển "Issued";
   - số đã cấp tăng đúng 600;
   - định mức của khối lượng đã làm = hao phí × khối lượng đã làm;
   - đã dùng = cấp − trả; chênh lệch = dùng − định mức;
   - cột chưa xong nên 600 kg vừa cấp thêm hiện là "Cấp trước khối lượng", không phải "Vượt định mức";
   - bảng trên màn hình hiện đúng các số đó.
3. **Chỉ huy trưởng, trên điện thoại:** xác nhận bảng chấm công đang chờ.
4. **Chi phí:**
   - quản lý dự án xem tổng (thực tế = vật tư + máy + nhân công) và bảng theo hạng mục;
   - kỹ sư thấy câu "không xem được chi phí".

**Clone sạch** (xuất các tệp của repo, kể cả tệp chưa commit, bằng `git ls-files -co --exclude-standard`; cổng 8891, stack `pmclone` chạy song song với stack dev):
- lần đầu bootstrap **hỏng ở bước tạo site** (nhóm vật tư tạo quá sớm, mục 7). Đã sửa, gỡ stack, chạy lại từ đầu: thoát mã 0;
- dữ liệu mẫu của lõi và lớp thi công dựng được:
  - kho công trường, 25 dòng kế hoạch vật tư;
  - máy đào có tài sản ERPNext ngay trên site mới;
  - cảnh báo vượt định mức và máy đến hạn bảo dưỡng;
- site mới có đủ index của các DocType mới, 12 quy tắc cảnh báo, vai trò Frappe kèm theo của Thủ kho và Kế toán dự án;
- kịch bản trình duyệt: thí điểm 23/23, vật tư-máy-nhân công 33/33, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20;
- smoke 0 lỗi;
- test: `project_manager` 282 + 17, `pm_construction` 51/51;
- bootstrap lần nữa trên dữ liệu đã có: thoát mã 0, smoke 0 lỗi, cảnh báo và quy tắc còn nguyên;
- site thứ hai chỉ có ERPNext và lõi:
  - lần đầu **hỏng 1 test** vì tên cây kho tiếng Việt (mục 7);
  - sau khi sửa, build lại: `project_manager` 282 + 17 trên site đó; `pm_construction` 51/51 và kịch bản vật tư 33/33 trên site đầy đủ, sau khi dựng lại dữ liệu mẫu;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 10. Điểm cần chú ý khi duyệt

- **Định mức và đơn giá của dữ liệu mẫu là số minh họa.** Khi thí điểm cần nhập định mức của doanh nghiệp, hoặc định mức nhà nước đang áp dụng.
- **Danh mục vật tư (Item) vẫn quản lý trong Desk của ERPNext.** Thủ kho hoặc quản trị tạo vật tư thuộc nhóm "Vật tư xây dựng" thì chúng hiện trong ô chọn.
- **Mua hàng (PO, PR, hóa đơn) làm trong Desk.** Hệ thống chưa có màn hình mua hàng riêng.
- **Phiếu kho chưa hủy được từ SPA:** muốn hủy thì hủy trong Desk, chi phí công tác tự tính lại.
- **Bảo dưỡng máy:** mới có ngày bảo dưỡng tiếp theo, lịch sử và cảnh báo; chưa nối với Asset Maintenance của ERPNext.
- **Giờ tăng ca chưa tính tiền** (mục 6).
- **Bảng định mức so với thực tế trả về mọi dòng của dự án.** Với BOQ rất lớn, trang tải chậm trên điện thoại; cần lọc theo hạng mục (để sau).
- **Năng suất (khối lượng / công), xung đột người và máy giữa các dự án** để M9 như kế hoạch.

## 11. Việc tiếp theo

**M9 — Hiệu suất, workload, nhiều dự án v2:** tỷ lệ đúng hạn, năng suất theo công đã chấm, workload và năng lực theo tuần, xung đột người và máy giữa các dự án, giới hạn ai xem hiệu suất của ai.
