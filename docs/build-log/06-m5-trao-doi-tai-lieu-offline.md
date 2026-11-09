# M5 — Trao đổi theo đầu việc, tài liệu, offline nền

## 1. Mục tiêu

Theo kế hoạch (prompt 4.7, 3.5):

- dòng thời gian của từng công việc và của dự án: bình luận, @nhắc tên, ảnh, tiến độ kèm ghi chú, các thay đổi;
- theo dõi và đánh dấu đã đọc; cập nhật ngay trên màn đang mở;
- ảnh hiện trường thu nhỏ trên máy trước khi gửi, ảnh nhỏ làm trong nền, kèm thời điểm và vị trí chụp;
- tài liệu dự án có phiên bản và duyệt, xem trước, tải về;
- tìm kiếm trong trao đổi và tài liệu;
- cài được như ứng dụng (PWA), có hàng đợi gửi lại khi mất mạng.

Tiêu chí hoàn thành: chụp ảnh khi tắt mạng → bật mạng → ảnh lên đúng công việc, không bị trùng.

## 2. DocType và hạ tầng mới

| DocType | Mục đích | Ghi chú |
|---|---|---|
| PM Media | Một ảnh gửi từ điện thoại hay máy tính | autoincrement; unique `client_uuid`; `object_key`, `thumb_key` trỏ vào MinIO; `taken_at`, `lat`, `lng` |
| PM Follow | Ai theo dõi trao đổi nào, đã đọc tới đâu | unique `(user, reference)`; mỗi người chỉ thấy dòng của mình |
| PM Document | Tài liệu dự án (bản vẽ, hợp đồng, biên bản…) | `PMD-.YYYY.-.#####`; mô tả bản mới nhất và bản đang dùng |
| PM Document Version | Một tệp của tài liệu | unique `(document, version_no)`; không sửa, không xóa; Nháp → Đã duyệt → Thay thế |

PM Activity (có từ M1) chứa bình luận với loại "Bình luận"; mục gắn một công việc giờ theo quyền xem công việc đó (xem mục 4).

**MinIO:**
- Hai service mới trong compose: `minio` (build từ mã nguồn Community, như `document_manager`) và `minio-init` (chạy một lần: tạo bucket `pm-files` và tài khoản riêng của ứng dụng, chỉ đọc ghi được bucket đó).
- Bootstrap tự sinh `MINIO_ROOT_PASSWORD`, `MINIO_APP_SECRET_KEY`; `configurator` ghi `pm_minio_*` vào `common_site_config.json`.
- MinIO không mở cổng ra ngoài: chỉ backend nói chuyện với nó.

**Thư viện mới:**
- `boto3==1.35.36` (Python): nói chuyện với MinIO.
- `socket.io-client@4.8.1` (SPA): realtime.

## 3. File chính

| File | Nội dung |
|---|---|
| `services/object_storage.py` | Ghi, đọc, đọc từng khúc, xóa đối tượng; khóa có dạng `minio:<site>/<loại>/<32 hex>`, khóa của site khác hay loại khác bị từ chối; dọn đối tượng không còn dòng nào trỏ tới |
| `services/files.py` | Gửi một đối tượng về trình duyệt theo từng khúc, chỉ hiện trực tiếp các kiểu an toàn (PDF, ảnh), còn lại là tải về; `nosniff` |
| `services/timeline.py` | Đọc từng trang (keyset), bình luận, @nhắc tên, theo dõi, đã đọc, ẩn bình luận của mình, realtime |
| `services/media.py` | Nhận ảnh, ảnh nhỏ trong nền, tường ảnh, gửi ảnh sau khi kiểm quyền |
| `services/documents.py` | Tài liệu, phiên bản, duyệt, tải về |
| `services/search_index.py` | Meilisearch: đưa vào chỉ mục sau commit, tìm trong phạm vi quyền, đối soát hằng đêm |
| `pwa.py` | Service worker ở `/pm/sw.js` |
| `api/activity.py`, `api/media.py`, `api/documents.py` | Lớp API mỏng |
| `frontend/src/lib/outbox.js`, `lib/sync.js` | Hàng đợi gửi lại (IndexedDB) và cách gửi từng loại |
| `frontend/src/lib/images.js` | Đọc EXIF (thời điểm, GPS) rồi thu nhỏ ảnh còn tối đa 1.600 px |
| `frontend/src/lib/realtime.js`, `lib/timeline.js`, `lib/pwa.js` | Realtime; phần không vẽ của dòng thời gian; đăng ký service worker |
| `frontend/src/components/timeline/*` | Dòng thời gian, ô soạn, lưới ảnh, xem ảnh lớn |
| `frontend/src/pages/project/DiscussionTab.vue`, `DocumentsTab.vue`, `pages/OutboxPage.vue` | Tab Trao đổi, tab Tài liệu, màn Hàng đợi gửi |
| `frontend/public/sw.js`, `manifest.json`, `icons/` | PWA |
| `docker/minio/*` | Image MinIO và MinIO client |
| `scripts/e2e/ui/discussion_flow.mjs`, `scripts/perf/timeline_check.py` | Kịch bản trình duyệt; đo dòng thời gian |

## 4. Quyết định kỹ thuật

- **Tệp tải qua máy chủ, không dùng URL ký của MinIO** (khác kế hoạch).
  - Mỗi lần xem ảnh hay tải tài liệu đều kiểm quyền; MinIO không phải mở ra Internet.
  - Tệp lớn được gửi theo từng khúc nên không chiếm bộ nhớ worker; ảnh nhỏ được trình duyệt giữ lâu vì một khóa không bao giờ đổi nội dung.
  - Đổi lại, một tệp 100 MB giữ một luồng gunicorn trong lúc tải. Nếu thành vấn đề thì thêm URL ký qua nginx sau.
- **Ai xem được thì trao đổi được:** không thêm quyền mới, khách (CĐT, TVGS) cũng bình luận được trên việc họ xem.
- **Quyền xem dòng thời gian chặt hơn trước:**
  - mục gắn một công việc theo quyền xem công việc đó, mục cấp dự án theo quyền xem dự án;
  - trước M5, tổ trưởng (chỉ xem việc được giao) vẫn đọc được trao đổi của việc khác qua `/api/resource/PM Activity`;
  - áp dụng chung cho PM Activity, PM Media, PM Document, PM Document Version.
- **@nhắc tên:**
  - ô soạn chèn `@[Tên](email)`;
  - máy chủ chỉ giữ người là thành viên xem được công việc, người khác thành chữ thường và không nhận thông báo.
- **Theo dõi:**
  - người viết, người được nhắc tên, người được giao việc tự theo dõi; ai cũng bật tắt được;
  - người theo dõi nhận thông báo khi có bình luận mới, trừ bình luận của chính mình.
- **Gửi một lần:**
  - ảnh và bình luận đều mang `client_uuid`, máy chủ trả lại bản đã có khi nhận lại;
  - ảnh gửi trước, bình luận gửi sau và gắn ảnh bằng chính các mã đó;
  - ảnh nào đã gửi xong thì lần thử lại không gửi nữa.
- **Hàng đợi gửi lại:**
  - lưu trong IndexedDB (ảnh lưu dạng ArrayBuffer, Safari cũng giữ được);
  - gửi theo thứ tự; lỗi có thể tự hết (mất mạng, máy chủ bận, hết phiên, token cũ) thì dừng và thử lại sau, lỗi máy chủ từ chối thì đánh dấu để người dùng thử lại hoặc bỏ;
  - thử lại khi có mạng, khi mở lại ứng dụng, mỗi 30 giây khi còn mục chờ;
  - mục của tài khoản khác trên cùng máy được giữ nguyên.
- **Báo tiến độ:** có mạng thì gửi thẳng (để máy chủ báo lỗi ngay, ví dụ thiếu lý do chậm); chỉ khi không có trả lời mới vào hàng đợi, với cùng mã.
- **Không gửi khi ứng dụng đã đóng (Background Sync):** service worker không có CSRF token của phiên. Mục chờ gửi khi mở lại ứng dụng, giống iPhone như kế hoạch đã tính.
- **Service worker:**
  - trang ứng dụng và dữ liệu đọc: lấy mạng trước, mất mạng thì dùng bản đã giữ;
  - JS/CSS: lấy bộ nhớ trước (tên đổi theo mỗi bản build);
  - ảnh nhỏ được giữ; không bao giờ giữ thao tác ghi;
  - đăng xuất xóa hết những gì đã giữ.
- **Trang đến từ bộ nhớ offline có thể mang CSRF token của phiên trước:** `api.js` tự xin token mới rồi gửi lại một lần.
- **Realtime:**
  - dùng Socket.IO của Frappe, mỗi màn công việc, dự án vào phòng của tài liệu đó (máy chủ kiểm quyền trước khi cho vào);
  - chỉ dùng WebSocket, vì long-polling cần sticky session và trả 400 với phiên đã mất khi offline;
  - xem mục 6 về hai chỉnh sửa hạ tầng cần thiết.
- **Tìm kiếm:**
  - một chỉ mục mỗi site;
  - lọc theo dự án ngay trong Meilisearch, lọc thêm theo công việc ở máy chủ cho người chỉ xem việc được giao;
  - chữ tìm được đánh dấu bằng ký tự riêng, màn hình tô đậm mà không dùng HTML;
  - mỗi đêm so số mục trong chỉ mục với cơ sở dữ liệu, lệch thì dựng lại rồi đổi chỉ mục (vẫn tìm được trong lúc dựng).
- **Tài liệu:**
  - chặn tệp chạy được và HTML, SVG;
  - tệp trùng hệt bản trước bị từ chối;
  - duyệt một bản thì bản đang dùng và các bản nháp cũ hơn thành "Thay thế".
- **Vị trí chụp:** ưu tiên GPS trong EXIF; ảnh không có thì dùng vị trí điện thoại khi người dùng bật nút "Vị trí" (ghi nhớ lựa chọn trên máy).

## 5. Kiểm thử

| Kiểm thử | Kết quả |
|---|---|
| `run-tests --app project_manager` | **237 + 17** (208 trước đó, 29 `test_timeline`; 17 `test_cpm` chạy riêng) |
| `test_timeline` | Bình luận, @nhắc tên, theo dõi, trang không trùng, ẩn, đã đọc, phạm vi quyền (tổ trưởng, người ngoài, API chỉ đọc); ảnh gửi trước bình luận, gửi hai lần vẫn một, chỉ nhận ảnh, thời điểm và vị trí, ảnh nhỏ, ai xem được ảnh; tài liệu, phiên bản, duyệt, tệp bị từ chối, tải về; tìm kiếm trong phạm vi (Meilisearch thật) |
| vitest (12 tệp) | **176/176** (thêm `outbox.test.js`, `timeline.test.js`, `discussion.test.js`, hai bài trong `api.test.js`: 32) |
| ruff (CI), `compileall`, `scripts/ci/check_repo.py` | Không lỗi |
| `scripts/e2e/ui/discussion_flow.mjs` | **27/27** trên Edge thật: điện thoại mất mạng, chụp ảnh và viết trao đổi, mở lại ứng dụng khi vẫn mất mạng, có mạng thì tự gửi, máy chủ có đúng 1 trao đổi và 1 ảnh đã thu nhỏ; báo tiến độ khi mất mạng; trao đổi chung, tìm kiếm, tường ảnh, tài liệu hai bản được duyệt, realtime; không cuộn ngang trên điện thoại |
| `forms_flow.mjs`, `schedule_flow.mjs` | 19/19, 28/28 (không hỏng gì của M3, M4) |
| Hiệu năng | Xem [HIEU_NANG.md](../HIEU_NANG.md#m5--dòng-thời-gian-50000-mục-2026-11-09) |

Lỗi tìm ra khi chạy kịch bản trình duyệt, đã sửa:
- **API gửi bình luận báo lỗi 500:** gọi sai `retry_on_deadlock`. Đã thêm test gọi qua lớp API.
- **Tường ảnh hiện cả ảnh chưa gắn vào bình luận:** trường số `activity_id` mặc định là 0, không phải trống.
- **Bản nháp cũ đứng mãi ở "Nháp"** sau khi bản mới hơn được duyệt.
- **Màn công việc không hiện tiến độ mới** khi báo cáo gửi bù tới máy chủ.
- **Tab Trao đổi tràn ngang 2 px trên điện thoại,** và chữ "Mất mạng" bị ẩn trên màn hẹp.
- **Realtime không chạy:** xem mục 6.

**Clone sạch** (xuất bằng `git checkout-index` sang thư mục mới, cổng 8891, stack `pmclone` chạy song song với stack dev):
- `bootstrap.ps1` thoát với mã 0, MinIO được build và `minio-init` tạo bucket; smoke 0 lỗi;
- `setup.demo.up` tạo được dự án mẫu kèm trao đổi, ảnh, bản vẽ;
- kịch bản trình duyệt: `forms_flow.mjs` 19/19, `schedule_flow.mjs` 28/28, `discussion_flow.mjs` 27/27;
- test: `project_manager` 237 + 17, `pm_construction` 2/2;
- bootstrap lần hai thoát với mã 0, smoke vẫn 0 lỗi, dữ liệu mẫu còn nguyên, ảnh vẫn đọc được từ MinIO, Giám sát báo MinIO và Meilisearch bình thường;
- đã gỡ stack (`down -v`) và xóa thư mục.

## 6. Điểm cần chú ý khi duyệt

- **Hai chỉnh sửa hạ tầng cho realtime:**
  - nginx của image Frappe gửi cho Socket.IO `Origin` là tên site nhưng giữ `Host` của trình duyệt; Frappe từ chối cặp này khi mở ứng dụng bằng tên khác (`localhost:8890`);
  - Frappe còn kiểm người dùng bằng cách gọi lại backend theo địa chỉ `Origin`, mà tên site không phân giải được trong container;
  - cách sửa: `docker/Dockerfile` đặt `Origin` và `Host` là `http://<site>:8000` cho đúng đoạn `/socket.io`, compose cho backend tên mạng trùng tên site;
  - không đụng tới mã nguồn Frappe.
- **MinIO build từ mã nguồn:** bootstrap lần đầu lâu thêm vài phút và cần mạng để tải Go module.
- **Tệp tải qua máy chủ thay vì URL ký** (mục 4).
- **Không có Background Sync:** mục chờ được gửi khi ứng dụng mở lại.
- **Danh mục loại tài liệu cố định** (Bản vẽ, Hợp đồng, Biên bản, Hồ sơ kỹ thuật, Thuyết minh/báo cáo, Pháp lý, Khác); sửa trong DocType nếu cần, chưa có màn quản lý.
- **Bình luận không sửa được,** chỉ người viết ẩn được (vẫn lưu). Đúng kế hoạch: không sửa, không xóa cứng.
- **Kiểm offline mới chạy trên Edge giả lập điện thoại** (Playwright tắt mạng), chưa thử trên máy thật, nhất là iPhone.
- **PWA cần HTTPS khi dùng ngoài `localhost`:** trình duyệt chỉ cho service worker chạy trên kết nối an toàn. Triển khai thật ở M11.
- **Dữ liệu mẫu** có thêm vài trao đổi có nhắc tên, một ảnh hiện trường và một bản vẽ hai bản (bản 1 đã duyệt, bản 2 chờ duyệt).

## 7. Việc tiếp theo

**M6 — Lớp thi công cơ bản:** BOQ (nhập Excel, phiên bản, sinh WBS), tiến độ theo khối lượng và giá trị dự toán, nhật ký thi công, nghiệm thu.
