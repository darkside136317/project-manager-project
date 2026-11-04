# M3 — Biểu mẫu động

## 1. Mục tiêu

Theo kế hoạch (prompt 4.8):

- người dùng tự thiết kế biểu mẫu (văn bản, số, ngày, chọn, hộp kiểm, bảng, ảnh, chữ ký), có phiên bản;
- biểu mẫu gắn với dự án, hạng mục hoặc công việc; quy trình Nháp → Đã nộp → Đã duyệt (hoặc Trả lại); in PDF, xuất Excel;
- công việc hoặc hạng mục có thể bắt buộc biểu mẫu đã duyệt mới được đóng;
- có sẵn gói mẫu chung; lớp thi công thêm gói riêng qua hook (M6).

Tiêu chí hoàn thành: tạo mẫu nghiệm thu → nộp trên điện thoại → duyệt → công việc đóng được.

## 2. DocType

| DocType | Mục đích | Ghi chú |
|---|---|---|
| PM Form Template (+PM Form Field) | Mẫu biểu mẫu, mỗi phiên bản một dòng, tên `{mã}-v01` | `status` (Nháp / Đang dùng / Ngừng dùng). Chỉ bản nháp sửa được; controller từ chối mọi thay đổi khác |
| PM Form Submission | Biểu mẫu đã điền | Gắn đúng phiên bản mẫu đã dùng; `state`, `data` (JSON), người nộp, người duyệt, `pdf_file`, `pdf_hash`, `client_uuid` (unique, cho hàng đợi gửi lại ở M5). Autoincrement; index `(project, template_code, state)`, `(task, template_code, state)`, `(submitted_by, state)`, `(state, project)` |
| PM Gate Requirement | Điều kiện đóng việc | `task`, `project`, `form_code` (theo mã, không theo phiên bản), `blocks`. M7 thêm điều kiện chuyển giai đoạn |

Thêm index `(task, name)` trên PM Activity: dòng thời gian của công việc nay gồm cả hoạt động của biểu mẫu.

Quyền toàn cục mới: `forms.manage` (Thiết kế mẫu biểu mẫu). Quản trị viên có sẵn; cấp cho nhóm khác ở trang Phân quyền.

## 3. File chính

| File | Nội dung |
|---|---|
| `services/form_templates.py` | Tạo, sửa nháp, đưa vào dùng, ngừng dùng, phiên bản mới, đọc định nghĩa (`spec`), cài gói mẫu |
| `services/forms.py` | Kiểm tra câu trả lời (`clean_data`), bắt đầu, lưu, nộp, duyệt, trả lại, bỏ nháp, gửi ảnh, danh sách, chờ tôi duyệt |
| `services/gates.py` | Điều kiện đóng việc: thêm, bỏ, kiểm tra, chép theo dự án mẫu |
| `services/form_output.py` + `templates/pm_form_print.html` | Bản in, PDF đã chốt, Excel |
| `services/text.py` | Bỏ dấu, tạo mã trường; dùng chung với nhập WBS |
| `setup/form_pack.py` | Gói mẫu chung: Phiếu kiểm tra hoàn thành công việc, Biên bản bàn giao, Báo cáo sự cố |
| `api/forms.py` | Lớp API mỏng |
| `overrides/task.py`, `services/rollup.py`, `services/progress.py` | Chặn đóng việc, nhóm chờ biểu mẫu |
| `frontend/src/components/forms/*` | `DynamicForm`, `FormTable`, `FormPictures`, `SignaturePad`, `TaskForms` |
| `frontend/src/pages/FormTemplatesPage.vue`, `FormTemplatePage.vue`, `FormSubmissionPage.vue`, `project/FormsTab.vue` | Danh sách mẫu, thiết kế, điền và duyệt, tab Biểu mẫu của dự án |
| `scripts/e2e/ui/forms_flow.mjs` | Kịch bản trình duyệt trọn luồng (Playwright, chạy trên máy tính và điện thoại) |

Tuyến mới: `/pm/bieu-mau-mau`, `/pm/bieu-mau-mau/:name`, `/pm/bieu-mau/:id`, `/pm/du-an/:id/bieu-mau`.

## 4. Quyết định kỹ thuật

- **Phiên bản không làm hỏng bản đã nộp.** Bản đang dùng bị đóng băng. Sửa nghĩa là tạo phiên bản mới; đưa bản mới vào dùng thì bản cũ chuyển sang Ngừng dùng. Biểu mẫu đã điền đọc đúng phiên bản nó đã dùng. `fieldname` giữ nguyên khi đổi nhãn, nên Excel ghép được số liệu của nhiều phiên bản.
- **Trạng thái do service giữ, không dùng Frappe Workflow.** Quyền duyệt phụ thuộc vai trò trong từng dự án (`task.approve`) hoặc việc là người duyệt của công việc đó; vai trò toàn cục của Workflow không diễn tả được.
- **Quyền:**
  - điền: người được cập nhật công việc trong dự án và thấy được công việc đó;
  - duyệt: `task.approve` trong dự án, hoặc người duyệt của công việc;
  - **người nộp không tự duyệt** biểu mẫu của mình (trừ quản trị viên).
- **Kiểm tra câu trả lời ở server, theo đúng phiên bản mẫu**, mỗi lần lưu; mục bắt buộc chỉ kiểm khi nộp. Số 0 là câu trả lời hợp lệ; giới hạn nhỏ nhất, lớn nhất lưu dạng chữ để 0 cũng là giới hạn.
- **Ảnh và chữ ký:**
  - tệp private, gắn vào đúng biểu mẫu; ai đọc được biểu mẫu mới đọc được ảnh;
  - chỉ nhận PNG, JPEG, WebP, nhận diện theo các byte đầu của tệp (không nhận SVG), tối đa 10 MB; điện thoại thu nhỏ ảnh còn cạnh dài 1600 px trước khi gửi;
  - câu trả lời chỉ được trỏ tới tệp của chính biểu mẫu đó, nên không thể mượn tệp riêng tư của người khác để in ra PDF.
- **Tự lưu:** điền đến đâu lưu đến đó (chờ 1,5 s sau lần gõ cuối); tải lại trang không mất nội dung.
- **PDF đã chốt:** tạo một lần khi duyệt (job queue `default`; job lỗi thì lần tải đầu tiên tạo), lưu tệp private kèm SHA-256. Đổi tên dự án sau đó không làm đổi bản đã duyệt. Bản chưa duyệt in kèm dòng "BẢN CHƯA DUYỆT" và không lưu.
- **Bản in dựng từ mẫu cố định, không cho người dùng viết mẫu in riêng:** câu trả lời luôn được escape (`autoescape`), ảnh nhúng dạng data URI, wkhtmltopdf chạy không truy cập tệp cục bộ. Font DejaVu có sẵn trong image, hiển thị đủ tiếng Việt.
- **Excel:** mỗi biểu mẫu một dòng, mỗi trường kiểu Bảng một sheet riêng. Ô chữ luôn lưu dạng chuỗi, nên nội dung bắt đầu bằng `=` không thành công thức.
- **Chặn đóng việc đặt ở `Task.validate`,** nên không đi vòng được qua báo tiến độ, duyệt việc, Kanban, Desk hay REST API:
  - việc không có người duyệt: phải có biểu mẫu đã duyệt mới báo 100% được;
  - việc có người duyệt: báo 100% khi biểu mẫu đã nộp, còn người duyệt chỉ đóng việc được khi biểu mẫu đã duyệt;
  - nhóm công việc: rollup giữ "Đang làm" (100%) cho đến khi biểu mẫu được duyệt, rồi tự tính lại.
- **Điều kiện theo mã mẫu:** biểu mẫu nộp trên phiên bản nào cũng được tính. Không ngừng dùng được một mẫu đang bị bắt buộc. Tạo dự án từ mẫu thì điều kiện được chép theo.
- **Gói mẫu cài một lần theo mã;** quản trị viên sửa hoặc ngừng dùng thì lần migrate sau không ghi đè. Lớp ngành thêm gói qua hook `pm_form_packs`.

## 5. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **152/152** (108 trước đó + 44 mới) |
| `test_forms` (44) | Phiên bản, kiểu dữ liệu, bảng và danh mục kiểm tra, tệp, quy trình và quyền, không tự duyệt, phạm vi danh sách, escape khi in, PDF giữ nguyên, Excel, chặn đóng việc qua mọi đường, nhóm chờ biểu mẫu, chép điều kiện từ mẫu |
| vitest (8 tệp) | **105/105** (thêm `forms.test.js`: 24) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/ui/forms_flow.mjs` | **19/19** kiểm tra trên Edge thật: thiết kế ở cỡ 1280 px; đặt điều kiện, điền, ảnh, ký, nộp, duyệt, PDF, Excel, đóng việc ở cỡ 390 px, có cảm ứng |

Lỗi kịch bản trình duyệt tìm được và đã sửa: trên trang thiết kế, ô nhãn trường bị bóp quá hẹp nên đọc không được. Việc báo xong thẳng 100% chưa ghi ngày bắt đầu thực tế (tìm khi xem ảnh chụp), đã sửa.

**Clone sạch:**
- Cách làm như M1, M2: xuất các file đã stage (`git checkout-index`) sang thư mục mới; `.env` từ `.env.example`, chỉ đổi tên compose, tiền tố volume và port (`pmclone`, 8891); để trống secret; chạy `bootstrap.ps1`.
- Kết quả, trên image build từ bản clone:
  - bootstrap tự sinh secret, tạo site, cài sẵn 3 mẫu chung;
  - smoke HTTP không lỗi (18/18 sau khi nạp dữ liệu mẫu);
  - `forms_flow.mjs` 19/19;
  - test `project_manager` 152/152, `pm_construction` 2/2;
  - PDF do worker tạo sau khi duyệt: 2/2 biểu mẫu đã duyệt có tệp lưu;
  - chạy bootstrap lần hai: không lỗi, smoke vẫn xanh.
- Sau đó gỡ stack clone kèm volume và xóa thư mục.

## 6. Điểm cần chú ý khi duyệt

- **Người nộp không tự duyệt được** (trừ quản trị viên). Đây là quyết định của tôi cho đúng tinh thần nghiệm thu; nếu đội ở công trường nhỏ cần tự duyệt, chỉ cần bỏ một điều kiện.
- **Mẫu in dùng bố cục cố định** cho mọi biểu mẫu, chưa theo đúng mẫu giấy của công ty. Khi có mẫu thật có thể thêm bố cục riêng, nhưng không cho nhập HTML tự do vì lý do an toàn.
- **Chữ ký là ảnh vẽ tay gắn với tài khoản đang đăng nhập,** không phải chữ ký số có giá trị pháp lý.
- **Ảnh tạm lưu trên volume `sites`.** MinIO vào M5 như kế hoạch.
- **Kịch bản trình duyệt chưa chạy trong CI:** chạy thủ công khi kiểm từng phase (xem DEV_WORKFLOW).
- **Phiên đăng nhập:** công cụ an toàn không cho Claude đọc mật khẩu admin, nên kiểm tra trình duyệt nay do kịch bản Playwright thực hiện; kịch bản tự đọc `docker/.env` như `smoke_http.py` và không in mật khẩu.

## 7. Việc tiếp theo

**M4 — Lịch trình và tiến độ trực quan:** phụ thuộc giữa các việc, đường găng, Gantt tự vẽ canvas, lịch thi công, baseline, đường cong S theo baseline.
