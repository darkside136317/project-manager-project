# Hướng dẫn sử dụng

Hệ thống mở ở `https://<tên miền>/pm` trên máy tính và điện thoại. Mỗi người thấy những gì vai trò của mình trong từng dự án cho phép. Một người có thể có vai trò khác nhau ở các dự án khác nhau.

Kịch bản trình diễn trên dữ liệu mẫu: [HUONG_DAN_THI_DIEM.md](HUONG_DAN_THI_DIEM.md). Cài đặt cho doanh nghiệp: [DEPLOYMENT.md](DEPLOYMENT.md).

## 1. Bắt đầu

- **Đăng nhập** bằng email và mật khẩu. Người dùng mới nhận liên kết đặt mật khẩu từ quản trị.
- **Thanh bên** chia ba nhóm:
  - Tổng quan: trang chủ, danh mục dự án, báo cáo;
  - Công việc: việc của tôi, cảnh báo, khối lượng công việc, hiệu suất, dự án;
  - Danh mục và Quản trị: hiện khi có quyền.
- **Ô "Đi tới"** (Ctrl K) tìm nhanh màn hình và dự án.
- **Chuông thông báo:** việc được giao, @nhắc tên, cảnh báo, phát sinh chờ duyệt, hồ sơ đã sẵn sàng…
- **Điện thoại:** mở `/pm` bằng Chrome (Android) hoặc Safari (iPhone) rồi chọn "Thêm vào màn hình chính". Khi mất mạng vẫn ghi được:
  - báo tiến độ, trao đổi, ảnh;
  - nhật ký thi công, đề xuất vật tư, ca máy, chấm công.
  
  Những gì ghi lúc đó nằm ở màn **Hàng đợi gửi** và tự gửi khi có mạng.

## 2. Vai trò trong dự án

| Vai trò | Làm gì |
|---|---|
| **Quản lý dự án** | Mọi việc trong dự án: kế hoạch, giao việc, thành viên, duyệt, ngân sách, duyệt phát sinh, đóng dự án, xem chi phí và hiệu suất |
| **Chỉ huy trưởng** | Kế hoạch, giao việc, duyệt nhật ký và nghiệm thu, xác nhận chấm công, kho, ghi rủi ro, lập phát sinh, xem hiệu suất trong dự án |
| **Kỹ sư** | Báo tiến độ, nhật ký thi công, đề xuất vật tư, ca máy, ghi rủi ro và vấn đề, lập phát sinh |
| **Tổ trưởng** | Chỉ thấy việc giao cho mình hoặc cho tổ mình; nhận việc, báo tiến độ, chấm công tổ |
| **Thủ kho** | Kho công trường: nhập, cấp phát, trả lại, hao hụt, điều chuyển |
| **Kế toán dự án** | Xem chi phí, lập ngân sách |
| **Khách** (chủ đầu tư, tư vấn giám sát) | Chỉ thấy việc được giao cho mình |

Ngoài vai trò trong dự án còn có quyền toàn công ty:
- **Giám đốc:** xem mọi dự án, hiệu suất, chi phí;
- **Quản trị:** người dùng, phân quyền, cấu hình.

## 3. Hằng ngày

**Việc của tôi:** những việc mình chịu trách nhiệm hoặc thực hiện.
- Việc mới giao cần **Nhận** hoặc **Từ chối** (kèm lý do).
- Bấm một việc để mở chi tiết: báo tiến độ (kéo thanh %, ghi chú, số công), xem trao đổi, ảnh, biểu mẫu.
- Việc đã trễ phải chọn **lý do chậm** và **khâu gây chậm** khi báo.

**Cảnh báo:** sắp đến hạn, quá hạn, nguy cơ trễ, chậm trên đường găng, chưa nhận việc, không cập nhật, quá tải, vấn đề quá hạn…
- "Đã biết" dừng leo thang. Cảnh báo tự hết khi điều kiện không còn.
- Chọn kênh nhận (ứng dụng, email) và giờ yên lặng ở menu tài khoản → Thông báo.

**Trao đổi** (tab Trao đổi, hoặc trong một công việc):
- bình luận, @nhắc tên, ảnh (tự thu nhỏ, ghi thời điểm và vị trí chụp), tệp;
- người được nhắc và người đang theo dõi được báo.

## 4. Lập và theo dõi dự án

1. **Dự án → Tạo dự án**, có thể từ một dự án mẫu. Thêm **thành viên** và vai trò ở tab Thành viên.
2. **Tab Công việc (WBS):**
   - cây giai đoạn, hạng mục, công việc; thêm, sửa, kéo thả để đổi chỗ;
   - giao người chịu trách nhiệm chính (mỗi việc đúng một người), người thực hiện, người duyệt;
   - nhập từ Excel (có tệp mẫu) hoặc **MS Project** (tệp XML); xuất ra MS Project.
3. **Tab Gantt:** kéo thanh để dời ngày, nối phụ thuộc. Hệ thống tính đường găng, cho xem trước những việc bị dời theo, rồi hỏi lý do. **Baseline** chụp kế hoạch đã duyệt để so sánh về sau.
4. **Kanban, Lịch, Ai làm gì:** cùng dữ liệu, nhìn theo trạng thái, theo ngày, theo người.
5. **Tab Tổng quan:**
   - sức khỏe (Xanh, Vàng, Đỏ) và lý do;
   - tiến độ so với kế hoạch, đường cong S, dự báo ngày xong;
   - giai đoạn hiện tại và điều kiện chuyển giai đoạn;
   - cảnh báo; kiểm soát dự án (rủi ro, vấn đề, phát sinh);
   - kết thúc dự án.
6. **Biểu mẫu:** quản trị thiết kế mẫu ở "Mẫu biểu mẫu". Người dùng nộp từ công việc, người duyệt duyệt hoặc trả lại. Bản đã duyệt được giữ dạng PDF; một việc có thể bắt buộc biểu mẫu đã duyệt mới đóng được.
7. **Tài liệu:** tải lên theo nhóm, có phiên bản và duyệt.

## 5. Thi công (lớp thi công)

- **BOQ:** nhập bảng khối lượng từ Excel. Duyệt BOQ sinh các hạng mục, công tác có khối lượng và đơn giá; tiến độ dự án tính theo giá trị dự toán.
- **Nhật ký:** mỗi ngày một nhật ký: thời tiết, nhân lực, khối lượng từng công tác, ảnh, vướng mắc. Kỹ sư nộp, chỉ huy trưởng xác nhận. Khối lượng trong nhật ký cập nhật tiến độ.
- **Nghiệm thu:** biên bản theo gói mẫu; khối lượng nghiệm thu được ghi vào công tác.
- **Vật tư:**
  - kho công trường; đề xuất (kỹ sư) rồi cấp phát (thủ kho);
  - trả lại, hao hụt, điều chuyển;
  - bảng định mức so với thực tế: "Vượt định mức" (đỏ, có cảnh báo) và "Cấp trước khối lượng" (vàng).
- **Máy:** máy đang ở công trường, ca máy và nhiên liệu, đưa máy vào và trả máy, **lịch đặt máy** (dự án khác đặt trùng ngày thì báo "Trùng lịch").
- **Chấm công:** tổ trưởng chấm theo ngày, mỗi người một công tác; chỉ huy trưởng xác nhận.
- **Chi phí:** chi phí thực tế (vật tư, máy, nhân công) so với dự toán và giá trị đã thi công. Chỉ người xem được chi phí mới thấy.

## 6. Kiểm soát dự án

- **Ngân sách:**
  - lập theo khoản mục và hạng mục, duyệt để dùng;
  - "Điều chỉnh" tạo bản mới từ bản đang dùng;
  - các chỉ số giá trị thu được: CPI dưới 1 là đang tốn hơn dự kiến, SPI dưới 1 là đang chậm.
- **Rủi ro, vấn đề:**
  - ghi rủi ro với khả năng, ảnh hưởng (1–5), người phụ trách, cách ứng phó, hạn;
  - rủi ro đã xảy ra thì bấm "Đã xảy ra" để mở vấn đề;
  - vấn đề có người xử lý và hạn; đóng phải ghi cách giải quyết.
- **Phát sinh:**
  - lập đề nghị (chi phí, số ngày, những việc dời ngày) rồi gửi duyệt;
  - quản lý dự án duyệt hoặc từ chối;
  - duyệt thì ngân sách tăng và các việc dời ngày.

## 7. Nhiều dự án

- **Danh mục dự án:** mọi dự án đang chạy mình được xem, dự án cần chú ý nhất ở trên. Có các cột sức khỏe, tiến độ, SPI, dự báo, giai đoạn, cảnh báo, việc quá hạn, tỷ lệ đúng hạn, người quá tải, xu hướng, chi phí so với giá trị làm được.
- **Khối lượng công việc:**
  - mỗi người theo tuần, so với số ngày công có thể làm; trên 120 % là quá tải;
  - xung đột người và máy giữa các dự án;
  - quản trị ghi nghỉ phép, bán thời gian ngay trong ô của tuần.
- **Hiệu suất:** việc xong, đúng hạn, trễ, năng suất tổ đội. Mỗi người xem được của chính mình; tổ trưởng xem tổ; quản lý xem người trong dự án mình.

## 8. Báo cáo

**Báo cáo** (thanh bên) gồm:

| Nhóm | Báo cáo |
|---|---|
| Tiến độ | Tiến độ các dự án, Công việc trễ |
| Nhân sự | Hiệu suất, Năng suất tổ đội |
| Tài chính | Ngân sách và EVM |
| Kiểm soát | Rủi ro, Vấn đề, Phát sinh |
| Thi công | Vật tư so với định mức, Chi phí so với dự toán |

Cách dùng:
- chọn bộ lọc rồi bấm "Xem báo cáo";
- xuất Excel, CSV, in hoặc PDF có đầu trang công ty;
- địa chỉ trang giữ cả bộ lọc, gửi cho người khác được;
- **Gửi theo lịch:** hằng ngày, tuần hoặc tháng, PDF hoặc Excel, cho những người cùng dự án. Mỗi người nhận chỉ thấy phần dữ liệu họ được xem.

## 9. Kết thúc dự án

Tab Tổng quan → **Kết thúc dự án** (quản lý dự án):
- xem những gì còn mở;
- **Xuất hồ sơ dự án (ZIP)**: danh sách công việc, thành viên, rủi ro, vấn đề, phát sinh, ngân sách, tài liệu, biểu mẫu đã duyệt, nhật ký thi công, BOQ, kèm `manifest.json` ghi mã kiểm tra của từng tệp. Lập xong thì có thông báo kèm liên kết tải;
- **Đóng dự án** (ghi kết luận): dự án ra khỏi các danh sách đang chạy, cảnh báo của nó kết thúc. Mở lại được khi cần.

## 10. Quản trị

- **Người dùng:** tạo tài khoản, gửi liên kết đặt mật khẩu, khóa hoặc mở tài khoản, gán nhóm quyền và phạm vi dự án (chỉ dự án tham gia, dự án được chọn, tất cả).
- **Phân quyền:** nhóm quyền toàn công ty; **vai trò trong dự án** (mỗi vai trò là một bộ quyền, sửa được).
- **Quy tắc cảnh báo:** bật, tắt, đổi số ngày, người nhận, các bậc leo thang.
- **Nghỉ phép, năng lực; Nhóm nhân viên; Thiết lập hệ thống.**
- **Nhật ký hệ thống:** ai làm gì, khi nào; xuất được, xóa bản cũ có xác nhận.
- **Giám sát hệ thống:** tình trạng các dịch vụ.
- **Danh mục** (công việc mẫu, lý do chậm, khâu gây chậm, định mức vật tư, máy, công nhân…) ở nhóm Danh mục của thanh bên.
