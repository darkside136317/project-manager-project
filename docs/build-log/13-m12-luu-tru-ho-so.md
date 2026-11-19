# M12 — Lưu trữ hồ sơ dự án trong hệ thống

## 1. Bối cảnh và lựa chọn

Kế hoạch M0–M11 chỉ để sẵn **điểm nối** cho lưu trữ (hook `project_close_handlers`, gói hồ sơ ZIP ở M10) và định làm một cầu nối riêng `pm_archive_bridge` sang `document_manager`. Sau M11, người dùng chọn **làm phần lưu trữ hồ sơ dự án ngay trong repo này, không qua cầu nối** (quyết định D21 trong [KE_HOACH.md](../KE_HOACH.md)).

Người dùng đã chốt:

| Câu hỏi | Lựa chọn |
|---|---|
| Ai quản lý hồ sơ lưu trữ | **Văn thư lưu trữ** của công ty (nhóm quyền mới "Lưu trữ") cho mọi dự án, cả dự án đã đóng; **quản lý dự án** lập hồ sơ trong dự án mình |
| Khi nào khóa hồ sơ | Khi đóng dự án, hồ sơ chuyển "Chờ nộp lưu"; **người lưu trữ duyệt "Nộp lưu"** thì mới khóa. Có cảnh báo nếu để quá lâu |
| Phạm vi đợt này | Lập hồ sơ, mục lục, khóa, tra cứu, kiểm toàn vẹn, **vị trí bản giấy** (kho, giá, hộp), **gói nộp lưu TT 05/2025/TT-BNV** |
| Để sau | Khai thác cho người ngoài dự án (phiếu yêu cầu, duyệt, hạn dùng); tiêu hủy hồ sơ hết hạn (đợt này chỉ hiện ngày hết hạn) |

## 2. Kiến trúc

- **App thứ ba `apps/pm_archive`**, cũng là một lớp:
  - phụ thuộc lõi (`required_apps`);
  - không import lớp thi công, lõi không biết nó;
  - lint `check_repo.py` nay kiểm cả việc một lớp không import lớp khác.
- **Lớp thi công góp danh mục** "Hồ sơ hoàn thành công trình" qua hook `pm_archive_categories`, khai báo trong `pm_construction/hooks.py` và do `pm_archive` đọc. Hai bên không import nhau.
- **Hook đã có được dùng lại:** `project_close_handlers`, `pm_dossier_parts` (qua `closing.data_parts`), `pm_spa_modules`, `pm_masters`, `pm_reports`, `pm_alert_types`, `pm_alert_rules`.
- **Thay đổi chung ở lõi** (không nhắc tới lưu trữ):

| Thay đổi | Để làm gì |
|---|---|
| Hook `pm_capabilities`, `pm_project_capabilities`; `extensions.capabilities()`, `project_capabilities()`, `builtin_capabilities()` | Lớp ngành khai báo quyền toàn cục và quyền trong dự án. Nhóm quyền, vai trò dự án, `policy` (quản trị có mọi quyền), màn phân quyền đọc chúng |
| Hook `pm_object_stores` | Lớp ngành có loại tệp riêng trên MinIO. `object_storage` nhận loại đó, và bộ dọn hằng đêm giữ các khóa lớp khai báo (thiếu bước này, tệp lưu trữ bị xóa sau 24 giờ) |
| `object_storage.put_stream` | Lưu một tệp lớn từ đĩa mà không giữ trong bộ nhớ (gói nộp lưu) |
| Hook `pm_nav_items` | Mục thanh bên của lớp ngành, theo quyền người xem |
| `closing.data_parts` | Dữ liệu dự án thành tệp (dự án, công việc, thành viên, rủi ro, ngân sách, phần của lớp ngành). Gói ZIP M10 và lưu trữ dùng chung |
| `create-site` cài các app của `PM_INSTALL_APPS` mà site chưa có | Lớp mới đến được site đang chạy: dev, clone, nâng cấp prod |

## 3. Mô hình dữ liệu

| DocType | Nội dung |
|---|---|
| **PM Archive Category** (cây) | Danh mục hồ sơ: mã, tên, thời hạn bảo quản (số năm hoặc Vĩnh viễn), bắt buộc khi nộp lưu, chế độ sử dụng (Nội bộ dự án / Hạn chế). Quy tắc xếp: nhóm tài liệu, mã mẫu biểu mẫu, mọi biểu mẫu còn lại, loại tư liệu (Ảnh, Trao đổi, Dữ liệu), đầu đường dẫn tệp dữ liệu |
| **PM Archive File** | Hồ sơ của một dự án theo một danh mục: số hồ sơ `<mã dự án>-<STT>`, tiêu đề, trạng thái (Đang lập → Chờ nộp lưu → Đã nộp lưu), thời gian, số tài liệu, số tờ, thời hạn và ngày hết hạn, chỗ để bản giấy, người và lúc nộp lưu, SHA-256 của hồ sơ, gói nộp lưu |
| **PM Archive Item** (autoincrement) | Một tài liệu trong hồ sơ: STT, loại, trích yếu, số ký hiệu, ngày, tác giả, số tờ. Trỏ tới tệp của dự án (khóa MinIO hoặc tệp Frappe), không chép, kèm SHA-256 |
| **PM Archive Storage** (cây) | Kho, phòng, giá, hộp |
| **PM Archive Check** | Một lần kiểm tra toàn vẹn: đã kiểm, bị đổi, bị mất, chi tiết |
| **PM Archive Settings** | Mã phông (mặc định viết tắt công ty), số phần chia kho để kiểm hằng tuần |

Tài liệu đã có của dự án được **tham chiếu, không chép**: bản tài liệu và ảnh không bao giờ đổi dưới khóa của chúng, ảnh chỉ bị ẩn mềm, PDF biểu mẫu đã duyệt được giữ nguyên. Những gì lớp lưu trữ tạo ra (dữ liệu dự án, trao đổi, bản scan, gói) nằm ở nhóm tệp `archive` của MinIO, nên có trong bản sao lưu.

## 4. Nghiệp vụ

1. **Lập hồ sơ** (`filing.compile`, chạy lại bao nhiêu lần cũng cho cùng kết quả): theo quy tắc của danh mục, xếp những gì chưa ở hồ sơ nào:
   - mọi bản tài liệu đã được duyệt; khi dự án đóng, thêm bản mới nhất của tài liệu chưa ai duyệt, có ghi chú;
   - biểu mẫu đã duyệt (PDF đã chốt);
   - ảnh hiện trường.

   Chạy khi bấm "Cập nhật hồ sơ", mỗi đêm cho dự án đang chạy, và khi đóng dự án. Tác giả ghi họ tên người tải lên.
2. **Quản lý dự án sửa trước khi khóa:** sắp thứ tự, sửa trích yếu, số ký hiệu, ngày, tác giả, số tờ; bỏ ra; chuyển sang hồ sơ khác; thêm bản scan; ghi chỗ để bản giấy; "Đề nghị nộp lưu".
3. **Khi đóng dự án:**
   - lập hồ sơ;
   - giữ dữ liệu dự án (`closing.data_parts`) và trao đổi;
   - mọi hồ sơ sang "Chờ nộp lưu" (ghi thời điểm);
   - liệt kê danh mục bắt buộc còn trống;
   - báo người lưu trữ và quản lý dự án.
4. **Nộp lưu** (người lưu trữ), một job ở hàng đợi `long` cho mỗi hồ sơ:
   - đọc từng tài liệu theo khúc, tính SHA-256. Nguồn đã có mã (bản tài liệu, PDF biểu mẫu) mà lệch thì dừng và ghi lý do;
   - bỏ hẳn các tài liệu đã bị bỏ ra;
   - ghi SHA-256 của cả hồ sơ (trên STT, mã, nguồn của từng tài liệu);
   - khóa.

   Sau đó:
   - không sửa, thêm, xóa tài liệu được nữa;
   - tài liệu gốc trong dự án (bản tài liệu, tài liệu, ảnh, biểu mẫu, tệp, chính dự án) không xóa được (`guards.py`);
   - tài liệu duyệt sau vào **hồ sơ bổ sung**.
5. **Kiểm tra toàn vẹn:** mỗi tuần một phần kho (mặc định 4 phần, cả kho mỗi tháng), hoặc người lưu trữ chạy tay. Tài liệu bị đổi hoặc bị mất được ghi lại và mở cảnh báo "Hồ sơ lưu trữ lỗi toàn vẹn".
6. **Cảnh báo "Hồ sơ chưa nộp lưu":** dự án đã đóng quá 90 ngày (sửa được ở quy tắc) mà còn hồ sơ chờ.

   Hai cảnh báo này báo cho quản lý dự án theo quy tắc, và báo thẳng cho người lưu trữ (`direct`), vì người lưu trữ không là thành viên dự án.
7. **Mục lục:** báo cáo "Mục lục hồ sơ" và "Mục lục văn bản trong hồ sơ" trên khung báo cáo M10, nên có sẵn Excel, CSV, PDF, in và gửi theo lịch.
8. **Gói nộp lưu** (TT 05/2025/TT-BNV, `AIP_hoso`):
   - bộ dựng gói sao chép từ `document_manager`: METS + EAD + PREMIS, kiểm METS bằng schema;
   - sửa để đọc tài liệu theo khúc từ MinIO vào ZIP, kiểm SHA-256 với mã lúc nộp lưu, và nhận mọi định dạng;
   - gói lưu ở MinIO (không giữ trong bộ nhớ), chỉ người lưu trữ lập và tải;
   - dữ liệu đặc tả: mã hồ sơ `<mã phông>.<năm>.<số hồ sơ>`, thời hạn bảo quản, chế độ sử dụng, số tài liệu, số tờ, chỗ để bản giấy; từng tài liệu có số ký hiệu, ngày, tác giả, trích yếu, loại, định dạng.
9. Xem, tải tài liệu lưu trữ, nộp lưu, lập gói đều ghi vào nhật ký hệ thống.

## 5. Phân quyền

| Ai | Được |
|---|---|
| Quản trị | Mọi thứ |
| Người lưu trữ (nhóm "Lưu trữ": `archive.manage_all`, `archive.view_all`) | Xem, nộp lưu, ghi chỗ để bản giấy (cả sau nộp lưu), lập gói, kiểm toàn vẹn ở **mọi dự án**, không cần là thành viên |
| Giám đốc (`archive.view_all`, cấp sẵn) | Xem mọi hồ sơ |
| Quản lý dự án (`archive.view`, `archive.manage` trong dự án) | Xem, lập hồ sơ dự án mình, kể cả hồ sơ "Hạn chế"; không nộp lưu |
| Chỉ huy trưởng, kế toán dự án (`archive.view`) | Xem, trừ hồ sơ "Hạn chế" (dữ liệu dự án có ngân sách) |
| Các vai trò khác | Không thấy |

Các quyền được thêm một lần vào vai trò dự án và nhóm quyền có sẵn; quản trị bỏ được về sau. Hook phạm vi trên hai DocType có cột `project`, đọc được qua API chung, ghi chỉ qua dịch vụ. `test_security` quét luôn 14 endpoint mới.

## 6. Giao diện

- **Tab "Hồ sơ lưu trữ"** của dự án (sau "Tài liệu"):
  - số hồ sơ theo trạng thái; danh mục bắt buộc còn thiếu;
  - danh sách hồ sơ;
  - nút Cập nhật hồ sơ, Đề nghị nộp lưu (quản lý), Nộp lưu các hồ sơ chờ (người lưu trữ).
- **Trang hồ sơ** `/pm/luu-tru/<hồ sơ>`:
  - thông tin, bản giấy (chọn chỗ để theo cây kho), các tài liệu;
  - sửa, sắp, bỏ ra, chuyển, thêm tệp;
  - mục lục (xem, Excel), Nộp lưu, Lập gói, Tải gói.
- **Trang "Lưu trữ hồ sơ"** `/pm/luu-tru` (thanh bên, cho ai đọc được ít nhất một hồ sơ; người lưu trữ thấy số hồ sơ chờ):
  - mọi hồ sơ, lọc theo trạng thái, năm, tìm trong tiêu đề, số hồ sơ, trích yếu;
  - lần kiểm tra toàn vẹn gần nhất; Kiểm tra toàn vẹn.
- **Danh mục hồ sơ, Kho lưu trữ:** màn cây của danh mục dùng chung.

## 7. Dữ liệu mẫu

`pm_archive.pm_archive.setup.demo.up`, chạy sau dữ liệu mẫu của lõi và lớp thi công:
- người lưu trữ `demo.luutru@pm.localhost`;
- kho A › giá 1 › hộp 1–3;
- hồ sơ đang lập của nhà phố và nhà xưởng;
- dự án đã bàn giao **DEMO-LT01** "Nhà kho vật tư": 5 tài liệu đã duyệt; dự án đã đóng nên hồ sơ chờ nộp lưu; hồ sơ hợp đồng đã nộp lưu, có số ký hiệu, số tờ, để ở hộp 1.

Gỡ: `demo.down` của lưu trữ trước các lớp khác.

## 8. Hiệu năng

`scripts/perf/archive_check.py`, chi tiết ở [HIEU_NANG.md](../HIEU_NANG.md#m12--lưu-trữ-hồ-sơ-dự-án-2026-11-18):
- một dự án có 2.000 ảnh thật trên MinIO và 300 tài liệu:
  - lập hồ sơ 1,0–1,4 s;
  - nộp lưu hồ sơ ảnh (SHA-256 từng đối tượng) 13,3 s, khoảng 150 tài liệu/s;
  - kiểm toàn vẹn 9 s;
- 15.000 hồ sơ, 1,5 triệu tài liệu:
  - danh sách lưu trữ 6–17 ms;
  - tìm trong trích yếu 0,55 s;
  - một hồ sơ 5.000 tài liệu 17 ms;
  - mục lục 14–144 ms.

Hai lần đo đầu dừng giữa chừng vì dữ liệu tạm của chính script: ngày 29/2 cộng 10 năm, và hàng đợi job của Frappe quá 500 sau nhiều lần chạy liền. Script nay chờ hàng đợi vơi rồi mới chạy.

## 9. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app pm_archive` | **21/21**: `test_install` 4 (phạm vi, hook, nhóm "Lưu trữ", quyền của vai trò), `test_filing` 9 (xếp đúng danh mục một lần; bản duyệt sau vào hồ sơ; quản lý sắp, sửa, bỏ, chuyển, thêm bản scan; đóng dự án; nộp lưu và khóa; chặn xóa nguồn; hồ sơ bổ sung; nguồn bị đổi thì không nộp lưu; kiểm toàn vẹn thấy tài liệu bị đổi và bị mất; nhắc hồ sơ chưa nộp lưu), `test_access` 4 (thành viên theo vai trò, người lưu trữ và giám đốc, ai lập ai nộp lưu, tải cần quyền và có nhật ký), `test_catalogue` 4 (mục lục theo quyền; gói nộp lưu: cấu trúc, dữ liệu đặc tả, nội dung; gói từ chối tài liệu đã đổi; chỉ hồ sơ đã nộp lưu có gói) |
| `run-tests --app project_manager` | **321 + 17** (trước: 317 + 17). Thêm `test_extensions` 4: quyền, kho tệp, mục thanh bên của lớp ngành, `data_parts`. Hai test cũ nay chịu được lớp ngành: chạy mọi báo cáo (bỏ báo cáo cần bộ lọc khác dự án), quyền của vai trò dự án (gồm quyền của lõi, lớp có thể thêm) |
| `run-tests --app pm_construction` | **58/58** |
| vitest | **227/227** (19 tệp; thêm `archive.layer.test.js`, 6 bài: tab và trang của lớp, chữ hiển thị, gửi bản scan, tab theo quyền) |
| `test_security` | Đạt, gồm 14 endpoint mới của `pm_archive` |
| `scripts/e2e/ui/archive_flow.mjs` | **31/31** trên Edge thật (mục 12) |
| `check_repo.py` (gồm lint mới: một lớp không import lớp khác), `scripts/ci` | 0 lỗi; 7/7 |

Ghi chú: trên stack dev, `test_assignments.test_accept_and_decline` có lần gặp deadlock khi chạy cả bộ lõi (chạy riêng thì đạt). Lỗi này có từ trước M12: scheduler của dev cộng dồn các dự án do test đánh dấu trong lúc giao dịch của test còn mở. CI chưa gặp lần nào.

## 10. Lỗi tìm ra, đã sửa

- **Cài lớp mới lên site đang chạy thất bại giữa chừng**: "No module named frappe.core.doctype.pm_archive_category".
  - Nguyên nhân: `after_install` tạo bản ghi của DocType vừa đồng bộ, trong khi bản đồ module và DocType của Frappe (dùng chung qua Redis) còn là bản cũ.
  - Hậu quả: site ghi nhận app đã cài nhưng không có bảng.
  - Sửa: lớp làm mới các bản đồ đó trước khi tạo dữ liệu (`_refresh_maps`); `migrate` dựng lại site dở dang.
- **Cây Frappe v16 không tự biết trường cha:** `NestedSet` cần khai báo `nsm_parent_field`.
- **Chèn hàng loạt thất bại** vì cột số của Frappe không nhận NULL.
- **Bộ dọn đối tượng hằng đêm sẽ xóa tệp của lớp mới.** Lõi chỉ biết khóa của ảnh và bản tài liệu; nay lớp khai báo khóa của mình (`pm_object_stores`).
- **Ghi họ tên tác giả** bị lỗi vì `frappe.local` không có `__dict__`. Phép đo bắt được, trước cả test.
- **Kịch bản đo không chạy hết được** vì lỗi trên; đã chạy lại sau khi sửa.

## 11. Điểm cần chú ý khi duyệt

- **Danh mục và thời hạn bảo quản mặc định là đề xuất.** Thi công dùng 10 năm, mức tối thiểu cao nhất (dự án nhóm A) của Nghị định 06/2021/NĐ-CP, khoản 4 Điều 26. Doanh nghiệp cần đối chiếu văn bản hợp nhất đang có hiệu lực và sửa trong "Danh mục hồ sơ".
- **Mã phông của gói nộp lưu** mặc định là viết tắt công ty (PM Archive Settings).
- **Gói nộp lưu nhận mọi định dạng** và ghi định dạng vào dữ liệu đặc tả. Nơi nhận có thể chỉ nhận một số định dạng: khi đó cần chuyển đổi trước (để sau).
- **Tài liệu được tham chiếu, không chép.** Điều này dựa vào việc nguồn không đổi dưới khóa và không bị xóa: lớp chặn xóa nguồn của hồ sơ đã nộp lưu, và kiểm toàn vẹn hằng tuần chứng minh lại. Xóa thẳng trong CSDL hay MinIO thì kiểm toàn vẹn sẽ báo.
- **Khai thác cho người ngoài dự án và tiêu hủy** để sau, như đã chốt.
- **Bảng tài liệu trên điện thoại** cuộn ngang bên trong khung bảng (trang không cuộn ngang). Sắp xếp và nộp lưu dành cho máy tính.

## 12. Tiêu chí hoàn thành, clone sạch

Theo kế hoạch đã duyệt:

| Tiêu chí | Kết quả |
|---|---|
| Lập hồ sơ theo danh mục, có thời hạn bảo quản | Đạt (mục 4, test `TestCompile`) |
| Đóng dự án thì chờ nộp lưu, báo danh mục còn thiếu | Đạt |
| Người lưu trữ nộp lưu thì khóa, có SHA-256, không xóa được nguồn | Đạt |
| Kiểm toàn vẹn định kỳ, cảnh báo | Đạt |
| Mục lục hồ sơ, mục lục văn bản; vị trí bản giấy | Đạt |
| Gói nộp lưu TT 05/2025/TT-BNV | Đạt (METS kiểm bằng schema, nội dung kiểm SHA-256) |
| Lớp mới cài lên site đang chạy (nâng cấp) | Đạt (clone sạch dưới đây) |

**Kịch bản trình duyệt** `archive_flow.mjs`, 31/31 trên Edge thật, ảnh trong `scripts/e2e/ui/out/archive/`:
1. **Quản lý dự án, máy tính:** tab hồ sơ của nhà phố (có hồ sơ, báo danh mục còn thiếu); cập nhật hồ sơ; sửa số ký hiệu một tài liệu; thêm bản scan; ghi chỗ để là hộp 2 của giá 1 kho A; không có nút nộp lưu.
2. **Người lưu trữ, máy tính** (không là thành viên dự án nào):
   - màn Lưu trữ hồ sơ thấy hồ sơ của các dự án, số hồ sơ chờ, mục thanh bên;
   - nộp lưu một hồ sơ chờ của DEMO-LT01: trạng thái chuyển Đã nộp lưu, có SHA-256, không còn nút sửa;
   - lập gói nộp lưu rồi tải về (ZIP);
   - mục lục văn bản ra Excel;
   - kiểm tra toàn vẹn không lỗi.
3. **Điện thoại:** chỉ huy trưởng thấy hồ sơ của nhà xưởng, không có nút cập nhật, không cuộn ngang; kỹ sư được báo không xem được.

Không có lỗi JavaScript.

**Clone sạch** theo **đường nâng cấp**: xuất các tệp của repo, kể cả tệp chưa commit (`git ls-files -co --exclude-standard`), cổng 8891, stack `pmclone`, chạy song song với stack dev.
- bootstrap lần đầu với `PM_INSTALL_APPS=erpnext project_manager pm_construction`, tức một bản M11: thoát mã 0, site chỉ có lõi và lớp thi công;
- bootstrap lần hai với mặc định: `create-site` báo "Installing pm_archive on pm.localhost", thoát mã 0, site có thêm `pm_archive`;
- **test chạy trước dữ liệu mẫu**, trên site vừa nâng cấp: `project_manager` 321 + 17, `pm_construction` 58/58, `pm_archive` 21/21;
- dữ liệu mẫu của lõi, lớp thi công, lưu trữ dựng được;
- site có:
  - 15 danh mục hồ sơ (10 của lưu trữ, 5 của lớp thi công);
  - nhóm "Lưu trữ"; giám đốc có `archive.view_all`; Quản lý dự án có `archive.view`, `archive.manage`;
  - 2 quy tắc cảnh báo mới; 2 job theo lịch (lập hồ sơ hằng đêm, kiểm toàn vẹn chủ nhật 02:30);
  - hồ sơ của ba dự án mẫu đúng như mục 7;
- smoke 0 lỗi;
- kịch bản trình duyệt: thí điểm 23/23, vật tư-máy-nhân công 33/33, khối lượng-hiệu suất 40/40, kiểm soát dự án 37/37, biểu mẫu 19/19, lịch trình 28/28, trao đổi 27/27, thi công 20/20, **lưu trữ 31/31**;
- bootstrap lần ba trên dữ liệu đã có: thoát mã 0, smoke 0 lỗi, cảnh báo (15) và quy tắc (16) còn nguyên;
- site chỉ có ERPNext và lõi: `project_manager` 321 + 17, 11 quy tắc cảnh báo của lõi;
- **site có ERPNext, lõi và lưu trữ, không có lớp thi công**: `pm_archive` 21/21, 10 danh mục. Lưu trữ không cần lớp thi công;
- đã gỡ stack (`down -v`, không dùng `--rmi`) và xóa thư mục.

Một clone sạch với site mới cài cả ba app cùng lúc (`new-site --install-app ...`) là việc của job `clean-clone` trên CI.
