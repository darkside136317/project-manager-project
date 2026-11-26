# Danh sách tính năng phần mềm quản lý dự án

Project Manager trên Frappe/ERPNext v16, bản hoàn thành giai đoạn M0–M12, tháng 11/2026.

Phần mềm gồm ba ứng dụng: lõi quản lý dự án dùng chung cho mọi ngành; lớp thi công xây dựng; lớp lưu trữ hồ sơ dự án. Phân hệ ghi “(lớp thi công)” hoặc “(lớp lưu trữ)” chỉ có khi cài lớp đó. Người dùng làm việc trên trình duyệt tại địa chỉ /pm, trên máy tính và điện thoại.

## 1. Phân hệ Giao diện làm việc

Cung cấp giao diện làm việc trên trình duyệt cho người dùng nội bộ, dùng được trên máy tính và điện thoại.

- Đăng nhập bằng email và mật khẩu; đổi mật khẩu; người dùng mới đặt mật khẩu qua liên kết do quản trị gửi;
- Thanh bên chia nhóm Tổng quan, Công việc, Danh mục, Quản trị; mỗi người chỉ thấy mục mình có quyền;
- Trang chủ; ô “Đi tới” (Ctrl K) tìm nhanh màn hình và dự án;
- Chuông thông báo: việc được giao, @nhắc tên, cảnh báo, phát sinh chờ duyệt, hồ sơ đã sẵn sàng;
- Màn hình đang mở tự cập nhật khi người khác trao đổi hoặc cập nhật (thời gian thực);
- Cài lên màn hình chính điện thoại như một ứng dụng; giao diện không cuộn ngang trên màn hình 390 px;
- Làm việc khi mất mạng: báo tiến độ, trao đổi, ảnh, nhật ký thi công, đề xuất vật tư, ca máy, chấm công được giữ ở màn “Hàng đợi gửi” và tự gửi khi có mạng, không tạo bản ghi trùng.

## 2. Phân hệ Quản lý dự án và cấu trúc công việc (WBS)

Quản lý danh sách dự án, thành viên, vai trò và cây công việc của từng dự án.

- Tạo dự án mới hoặc tạo từ dự án mẫu (chép sẵn cây công việc);
- Quản lý thành viên dự án theo vai trò; một người có thể giữ vai trò khác nhau ở các dự án khác nhau; thành viên có hiệu lực theo ngày;
- Cây công việc: giai đoạn, hạng mục, công việc; thêm mới, sửa, hủy, kéo thả để đổi chỗ (mang theo nhánh con);
- Nhập cây công việc từ Excel theo tệp mẫu, có chạy thử để báo mọi lỗi trước khi ghi;
- Nhập, xuất MS Project (XML): cây công việc, ngày, mốc, phụ thuộc, người phụ trách;
- Tiến độ tự cộng dồn từ công việc lên hạng mục, giai đoạn và dự án;
- Trang tổng quan dự án: sức khỏe Xanh, Vàng, Đỏ kèm lý do; tiến độ so với kế hoạch; đường cong S; dự báo ngày hoàn thành; giai đoạn hiện tại; cảnh báo; rủi ro, vấn đề, phát sinh;
- Kết thúc dự án: xem những gì còn mở; đóng dự án có ghi kết luận; mở lại khi cần;
- Xuất hồ sơ dự án dạng ZIP: công việc, thành viên, rủi ro, vấn đề, phát sinh, ngân sách, tài liệu, biểu mẫu đã duyệt, nhật ký thi công, BOQ, kèm danh sách mã kiểm tra SHA-256 của từng tệp.

## 3. Phân hệ Giao việc và cập nhật tiến độ

Giao việc rõ trách nhiệm và theo dõi tiến độ thực hiện từng công việc.

- Mỗi công việc có đúng một người chịu trách nhiệm chính; thêm người thực hiện, người duyệt, người theo dõi;
- Giao việc cho cá nhân, đội, tổ hoặc nhà thầu phụ; tổ trưởng chỉ thấy việc giao cho mình hoặc cho tổ mình;
- Nhận hoặc từ chối việc (kèm lý do); thu hồi, đổi người; lịch sử giao việc không xóa được;
- Màn “Việc của tôi”: những việc mình chịu trách nhiệm hoặc thực hiện;
- Báo tiến độ theo phần trăm, kèm ghi chú và số công; gửi lại nhiều lần không bị trùng;
- Việc đã trễ bắt buộc chọn lý do chậm và khâu gây chậm khi báo tiến độ;
- Đổi hạn sau khi đã giao việc phải ghi lý do; lưu lịch sử đổi người, đổi hạn;
- Xem cùng dữ liệu theo nhiều cách: Kanban theo trạng thái, Lịch theo ngày, “Ai làm gì” theo người.

## 4. Phân hệ Lập lịch, Gantt và baseline

Lập kế hoạch thời gian, tính đường găng và so sánh với kế hoạch đã duyệt.

- Phụ thuộc giữa công việc (FS, SS, FF, SF) có độ trễ; phát hiện phụ thuộc vòng tròn;
- Tính đường găng ở máy chủ theo ngày làm việc, trừ ngày nghỉ và ngày lễ;
- Biểu đồ Gantt: kéo thanh để dời ngày, nối phụ thuộc, tô đường găng; trên điện thoại chỉ xem;
- Xem trước những việc bị dời theo trước khi áp dụng; bắt buộc ghi lý do; lưu lịch sử thay đổi;
- Lịch thi công theo ngày;
- Baseline nhiều phiên bản; so sánh kế hoạch hiện tại với baseline trên Gantt và trên bảng;
- Đường cong S kế hoạch và thực tế; số ngày chênh lệch; dự báo ngày hoàn thành.

## 5. Phân hệ Biểu mẫu động

Cho phép doanh nghiệp tự thiết kế biểu mẫu, nộp, duyệt và giữ bản đã duyệt.

- Thiết kế mẫu với các loại trường: văn bản, số, ngày, danh sách chọn, hộp kiểm, bảng, ảnh, chữ ký;
- Mẫu có phiên bản; mẫu đang dùng được khóa; đổi phiên bản không ảnh hưởng biểu mẫu đã nộp;
- Biểu mẫu gắn với dự án, hạng mục hoặc công việc; quy trình Nháp, Đã nộp, Đã duyệt hoặc Trả lại;
- Chụp ảnh và ký tay ngay trên điện thoại;
- In PDF, xuất Excel; bản đã duyệt được giữ dạng PDF;
- Cấu hình bắt buộc có biểu mẫu đã duyệt thì mới đóng được công việc, hạng mục;
- Gói biểu mẫu có sẵn khi cài; lớp ngành thêm gói riêng (ví dụ gói biên bản nghiệm thu của lớp thi công).

## 6. Phân hệ Trao đổi, tài liệu và ảnh hiện trường

Trao đổi theo từng công việc và dự án; quản lý tài liệu và ảnh hiện trường.

- Bình luận, @nhắc tên, đính kèm ảnh và tệp; dòng thời gian gồm cả tiến độ và thay đổi của công việc;
- Theo dõi công việc, đánh dấu đã đọc, nhận thông báo khi có trao đổi mới;
- Ảnh hiện trường tự thu nhỏ trên máy trước khi gửi, có ảnh nhỏ, ghi thời điểm và vị trí chụp;
- Tài liệu dự án theo nhóm, có phiên bản và duyệt; xem trước, tải về;
- Tìm kiếm toàn văn trong trao đổi và tài liệu, trong phạm vi quyền của người tìm;
- Chỉ người xem được công việc mới đọc được trao đổi, ảnh, tài liệu của công việc đó.

## 7. Phân hệ Cảnh báo, thông báo và chuyển giai đoạn

Phát hiện sớm nguy cơ chậm tiến độ, báo đúng người và theo dõi đến khi được xử lý.

- Sức khỏe Xanh, Vàng, Đỏ của công việc, giai đoạn và dự án; dự báo trễ;
- Cảnh báo của lõi: sắp đến hạn, quá hạn, nguy cơ trễ, chậm trên đường găng, sức khỏe dự án xấu đi, chưa nhận việc, không cập nhật tiến độ, biểu mẫu chờ duyệt, chờ duyệt chuyển giai đoạn, quá tải công việc, vấn đề quá hạn xử lý;
- Cảnh báo của lớp ngành: thiếu nhật ký thi công, vượt định mức vật tư, máy đến hạn bảo dưỡng (lớp thi công); hồ sơ chưa nộp lưu, hồ sơ lưu trữ lỗi toàn vẹn (lớp lưu trữ);
- Quy tắc cảnh báo cấu hình được: bật, tắt, số ngày, người nhận (người chịu trách nhiệm, người thực hiện, người duyệt, người theo dõi, quản lý dự án, theo vai trò, cấp trên);
- Leo thang theo bậc khi sau một số ngày không ai xác nhận; bấm “Đã biết” thì dừng leo thang; cảnh báo tự kết thúc khi điều kiện không còn;
- Không gửi trùng: mỗi đợt một cảnh báo, mỗi người mỗi bậc nhận một lần;
- Mỗi người chọn kênh nhận (ứng dụng, email), giờ yên lặng và tắt loại cảnh báo không cần;
- Tóm tắt công việc hằng ngày và hằng tuần qua email;
- Chuyển giai đoạn dự án theo điều kiện: tự động, cần duyệt hoặc thủ công; lớp ngành thêm điều kiện riêng (lớp thi công: mọi công tác của giai đoạn đã nghiệm thu đủ).

## 8. Phân hệ Nguồn lực và hiệu suất

Theo dõi tải công việc của từng người, xung đột nguồn lực giữa các dự án và hiệu suất làm việc.

- Khối lượng công việc theo tuần so với năng lực (ngày làm việc trừ nghỉ phép, bán thời gian); trên 120 % là quá tải và có cảnh báo;
- Ghi nghỉ phép, làm bán thời gian ngay trong ô của tuần;
- Phát hiện xung đột người giữa các dự án; lớp thi công thêm xung đột máy;
- Hiệu suất cá nhân: số việc xong, tỷ lệ đúng hạn, việc trễ, việc đang trễ, việc báo tiến độ;
- Năng suất tổ đội = khối lượng làm được / số công (lớp thi công: từ nhật ký và chấm công đã xác nhận);
- Lưu số liệu hiệu suất hằng tuần để xem xu hướng;
- Phạm vi xem: mỗi người xem của chính mình; tổ trưởng xem tổ; quản lý xem người trong dự án mình; giám đốc xem tất cả.

## 9. Phân hệ Danh mục dự án

Tổng hợp tình hình mọi dự án đang chạy mà người dùng được xem; dự án cần chú ý nhất đứng đầu.

- Các cột: sức khỏe, tiến độ, SPI, dự báo ngày xong, giai đoạn, cảnh báo, việc quá hạn, tỷ lệ đúng hạn 4 tuần, người quá tải, xu hướng tiến độ;
- Lớp ngành thêm cột riêng (lớp thi công: chi phí so với giá trị làm được, vượt định mức vật tư).

## 10. Phân hệ Kiểm soát dự án

Kiểm soát ngân sách, rủi ro, vấn đề và thay đổi (phát sinh) của dự án.

- Ngân sách theo khoản mục và hạng mục, có phiên bản, duyệt rồi mới dùng; “Điều chỉnh” tạo bản mới từ bản đang dùng;
- Chỉ số giá trị thu được (EVM): BAC, PV, EV, AC, CPI, SPI, EAC, VAC;
- Sổ rủi ro: khả năng và ảnh hưởng (1–5), người phụ trách, cách ứng phó, hạn; rủi ro “Đã xảy ra” chuyển thành vấn đề;
- Vấn đề có người xử lý và hạn; đóng vấn đề phải ghi cách giải quyết; cảnh báo vấn đề quá hạn;
- Phát sinh: đề nghị chi phí, số ngày và những việc phải dời; gửi quản lý dự án duyệt hoặc từ chối; duyệt thì ngân sách tăng và các việc tự dời ngày.

## 11. Phân hệ Khối lượng, nhật ký và nghiệm thu (lớp thi công)

Quản lý khối lượng thi công theo BOQ, nhật ký công trường và nghiệm thu.

- Nhập BOQ (bảng khối lượng) từ Excel, có phiên bản; duyệt BOQ sinh hạng mục và công tác có khối lượng, đơn giá;
- Tiến độ dự án tính theo khối lượng, cộng dồn theo giá trị dự toán;
- Nhật ký thi công hằng ngày: thời tiết, nhân lực, khối lượng từng công tác, ảnh, vướng mắc; ghi được khi mất mạng;
- Kỹ sư nộp nhật ký, chỉ huy trưởng xác nhận; khối lượng trong nhật ký cập nhật tiến độ công tác;
- Nghiệm thu theo gói biên bản mẫu; khối lượng nghiệm thu được ghi vào công tác;
- Cảnh báo thiếu nhật ký; giai đoạn chỉ chuyển khi mọi công tác đã nghiệm thu đủ.

## 12. Phân hệ Vật tư, máy, nhân công và chi phí (lớp thi công)

Quản lý vật tư, máy thi công, nhân công và chi phí thực tế của công trường.

- Kho công trường theo từng dự án;
- Đề xuất vật tư theo công tác (cả khi mất mạng); nhập kho, cấp phát, trả lại, hao hụt, điều chuyển;
- Định mức vật tư; so sánh định mức với thực tế: “Vượt định mức” (có cảnh báo) và “Cấp trước khối lượng”;
- Máy của công ty (gắn tài sản) và máy thuê; đưa máy vào, trả máy; ca máy và nhiên liệu; bảo dưỡng;
- Lịch đặt máy; báo “Trùng lịch” khi dự án khác đặt cùng ngày;
- Tổ đội, công nhân; chấm công theo ngày, mỗi người một công tác; chỉ huy trưởng xác nhận;
- Chi phí thực tế (vật tư, máy, nhân công) so với dự toán và giá trị đã thi công; chỉ người có quyền xem chi phí mới thấy.

## 13. Phân hệ Lập hồ sơ lưu trữ (lớp lưu trữ)

Hình thành hồ sơ lưu trữ của dự án ngay trong lúc thực hiện, mỗi danh mục hồ sơ một hồ sơ.

- Tự xếp tài liệu đã duyệt, biểu mẫu đã duyệt, ảnh hiện trường vào đúng hồ sơ theo quy tắc của danh mục; chạy khi bấm “Cập nhật hồ sơ” và tự chạy mỗi đêm;
- Thông tin hồ sơ: số hồ sơ, tiêu đề, thời gian, thời hạn bảo quản, ngày hết hạn bảo quản, chế độ truy cập;
- Mục lục văn bản trong hồ sơ: sắp lại thứ tự; sửa số ký hiệu, ngày, tác giả, số tờ, trích yếu;
- Bỏ một tài liệu ra khỏi hồ sơ hoặc chuyển sang hồ sơ khác;
- Thêm tệp ngoài hệ thống: bản scan biên bản ký tay, tài liệu giấy;
- “Còn thiếu”: liệt kê danh mục bắt buộc chưa có tài liệu;
- Khi đóng dự án: xếp nốt tài liệu, giữ dữ liệu dự án và toàn bộ trao đổi, chuyển hồ sơ sang “Chờ nộp lưu” và báo người lưu trữ; quản lý dự án có thể “Đề nghị nộp lưu” sớm hơn;
- Tra cứu hồ sơ theo trạng thái, năm; tìm theo tiêu đề và trích yếu (người lưu trữ thấy hồ sơ của mọi dự án);
- Hồ sơ “Hạn chế” (dữ liệu dự án có ngân sách): chỉ người lập hồ sơ và người có quyền lưu trữ xem.

## 14. Phân hệ Nộp lưu và bảo quản hồ sơ (lớp lưu trữ)

Khóa hồ sơ sau khi nộp lưu, bảo đảm toàn vẹn và quản lý bản giấy.

- Người lưu trữ duyệt “Nộp lưu”: tính mã kiểm tra SHA-256 của từng tài liệu và của cả hồ sơ, rồi khóa hồ sơ chỉ đọc;
- Sau khi nộp lưu, tài liệu gốc trong dự án không xóa được; tài liệu duyệt sau đó vào hồ sơ bổ sung;
- Kiểm tra toàn vẹn tự động mỗi tuần (xoay vòng một phần kho), chạy tay được; cảnh báo khi tài liệu bị đổi hoặc bị mất;
- Cảnh báo hồ sơ chưa nộp lưu sau một số ngày kể từ khi đóng dự án (mặc định 90 ngày);
- Kho lưu trữ bản giấy dạng cây: kho, phòng, giá, hộp; ghi vị trí bản giấy của từng hồ sơ;
- Mục lục hồ sơ và mục lục văn bản: xuất Excel, PDF, in;
- Lập gói nộp lưu theo Thông tư 05/2025/TT-BNV (METS, EAD, PREMIS) dạng ZIP; từ chối lập gói nếu tài liệu đã bị thay đổi;
- Ghi nhật ký mỗi lần mở hoặc tải tài liệu lưu trữ, nộp lưu, lập và tải gói nộp lưu.

## 15. Phân hệ Thống kê, báo cáo

Tổng hợp, thống kê và kết xuất báo cáo phục vụ điều hành dự án.

- Báo cáo tiến độ: tiến độ các dự án, công việc trễ;
- Báo cáo nhân sự: hiệu suất, năng suất tổ đội;
- Báo cáo tài chính: ngân sách và EVM;
- Báo cáo kiểm soát: rủi ro, vấn đề, phát sinh;
- Báo cáo thi công: vật tư so với định mức, chi phí so với dự toán (lớp thi công);
- Báo cáo lưu trữ: mục lục hồ sơ, mục lục văn bản trong hồ sơ (lớp lưu trữ);
- Lọc dữ liệu; xuất Excel, CSV, in hoặc PDF có đầu trang công ty; đường dẫn trang giữ nguyên bộ lọc để gửi cho người khác;
- Gửi báo cáo theo lịch (hằng ngày, tuần, tháng; PDF hoặc Excel); mỗi người nhận chỉ thấy phần dữ liệu họ được xem.

## 16. Phân hệ Xuất, nhập dữ liệu

Trao đổi dữ liệu với Excel, MS Project và cơ quan lưu trữ khác.

- Nhập cây công việc từ Excel theo tệp mẫu, có chạy thử;
- Nhập, xuất kế hoạch dạng MS Project XML;
- Nhập BOQ từ Excel (lớp thi công);
- Xuất biểu mẫu ra PDF, Excel; xuất báo cáo ra Excel, CSV, PDF;
- Xuất hồ sơ dự án dạng ZIP kèm danh sách mã kiểm tra SHA-256;
- Xuất gói nộp lưu theo Thông tư 05/2025/TT-BNV, gồm tệp XML METS, EAD, PREMIS (lớp lưu trữ);
- Xuất nhật ký hệ thống.

## 17. Phân hệ Danh mục dùng chung

Quản lý các danh mục dùng chung phục vụ chuẩn hóa dữ liệu.

- Loại nút WBS; vai trò trong dự án; đội, tổ; lý do chậm; khâu gây chậm;
- Mẫu biểu mẫu; dự án mẫu;
- Lịch nghỉ có ngày lễ Việt Nam, công ty, năm tài chính, kho (tạo sẵn khi cài);
- Định mức vật tư, máy thi công, công nhân (lớp thi công);
- Danh mục hồ sơ dạng cây (thời hạn bảo quản, bắt buộc hay không, quy tắc tự xếp tài liệu) và kho lưu trữ (lớp lưu trữ).

## 18. Phân hệ Quản trị hệ thống

Cung cấp công cụ quản trị, cấu hình và giám sát vận hành hệ thống.

- Quản lý người sử dụng: thêm mới, sửa, khóa hoặc mở, xóa, tìm kiếm; gửi liên kết đặt mật khẩu;
- Nhóm quyền toàn công ty (Giám đốc, Lưu trữ, Quản trị…) sửa được, sao chép được;
- Vai trò trong dự án: mỗi vai trò là một bộ quyền sửa được;
- Phạm vi dự án của từng người dùng: chỉ dự án tham gia, dự án được chọn, hoặc tất cả;
- Bảng tổng hợp quyền theo nhóm và vai trò;
- Nhóm nhân viên; nghỉ phép và năng lực; quy tắc cảnh báo; thiết lập hệ thống;
- Nhật ký hệ thống: ai làm gì, khi nào; tìm kiếm, xuất, xem trước rồi xóa bản cũ có xác nhận;
- Giám sát hệ thống: tình trạng các dịch vụ, hàng đợi, tiến trình xử lý nền, dung lượng tệp.

## 19. Phân hệ Triển khai, sao lưu và khôi phục

Cài đặt, nâng cấp, vận hành và bảo vệ dữ liệu của hệ thống.

- Cài đặt bằng một lệnh (script cho Windows và cho Linux, macOS); tự sinh mật khẩu; chạy lại không hỏng; tự cấu hình ERPNext;
- Triển khai lên máy chủ có tên miền và HTTPS; kiểm tra tệp cấu hình trước khi chạy;
- Cài thêm lớp ngành lên hệ thống đang chạy khi nâng cấp; chỉ cài lõi cho ngành khác ngoài xây dựng;
- Sao lưu cơ sở dữ liệu, tệp, khóa mã hóa và kho tệp, kèm danh sách mã kiểm tra SHA-256;
- Khôi phục sang máy khác;
- Dữ liệu mẫu để trình diễn và thí điểm.

## Đảm bảo yêu cầu an toàn, bảo mật và hiệu năng

- Phân quyền theo dự án áp dụng cho mọi truy vấn (danh sách, báo cáo, tìm kiếm, ô chọn liên kết), cả với kho và mua hàng của ERPNext;
- Tệp lưu riêng tư: kho tệp không mở ra ngoài, mỗi lần tải đều kiểm quyền; chỉ PDF và ảnh mở trực tiếp trong trình duyệt;
- Không chức năng nào mở cho người chưa đăng nhập; thao tác ghi chỉ nhận yêu cầu POST; tài khoản không phải nhân viên bị từ chối; nội dung in và dữ liệu nhúng được lọc ký tự đặc biệt;
- Nhật ký hệ thống ghi các thao tác quan trọng: tải tệp, xuất dữ liệu, cập nhật, nộp lưu;
- Hồ sơ đã nộp lưu, gói hồ sơ dự án và bản sao lưu đều có mã kiểm tra SHA-256; hồ sơ lưu trữ được kiểm tra định kỳ;
- Gửi lại dữ liệu sau khi mất mạng không tạo bản ghi trùng;
- Đã đo trên dữ liệu lớn: 1 triệu công việc, 5 triệu trao đổi, 2 triệu ảnh, 100 nghìn phiếu kho, 500 người; 200 người báo tiến độ cùng lúc không mất dữ liệu; 15.000 hồ sơ lưu trữ với 1,5 triệu tài liệu;
- Không sửa mã nguồn ERPNext; các phiên bản phần mềm được ghim để nâng cấp có kiểm soát.

## Chưa có trong phiên bản này

- Khai thác hồ sơ lưu trữ cho người ngoài dự án (phiếu yêu cầu, duyệt, hạn sử dụng);
- Hết hạn bảo quản và tiêu hủy hồ sơ (hiện mới hiện ngày hết hạn bảo quản);
- Cổng thông tin riêng cho chủ đầu tư, tư vấn giám sát (hiện họ là “Khách”, chỉ thấy việc được giao);
- Gửi thông báo qua Zalo, SMS; trợ lý AI.
