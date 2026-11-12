# Hướng dẫn thí điểm

Thí điểm bắt đầu sau M7, khi hệ thống đã có lõi quản lý dự án, lớp thi công (BOQ, nhật ký, nghiệm thu) và cảnh báo. Tài liệu này dành cho người tổ chức thí điểm: cách dựng hệ thống, kịch bản demo trên dữ liệu mẫu, cách đưa một công trình thật vào, những gì cần quan sát và giới hạn hiện tại.

## 1. Dựng hệ thống

Trên máy có Docker (Windows: Docker Desktop), từ thư mục repo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Linux, macOS:

```bash
bash scripts/bootstrap.sh
```

Bootstrap làm các việc sau:
- tạo `docker/.env` và sinh mật khẩu;
- build image, tạo site, chạy thiết lập ERPNext;
- cài các quy tắc cảnh báo mặc định.

Sau đó dựng dữ liệu mẫu (trong thư mục `docker/`): trước là dự án nhà phố của lõi, rồi đến dự án nhà xưởng của lớp thi công.

```bash
docker compose exec backend bench --site pm.localhost execute project_manager.project_manager.setup.demo.up
```

```bash
docker compose exec backend bench --site pm.localhost execute pm_construction.pm_construction.setup.demo.up
```

Địa chỉ:
- ứng dụng: `http://localhost:8890/pm`;
- ERPNext Desk: `http://localhost:8890/app`.

Tài khoản quản trị là `Administrator`; mật khẩu nằm trong `docker/.env` (biến `ADMIN_PASSWORD`).

**Người dùng mẫu** (chưa có mật khẩu):

| Tài khoản | Người | Vai trò trong dự án |
|---|---|---|
| `demo.quanly@pm.localhost` | Trần Quản Lý | Quản lý dự án |
| `demo.chihuy@pm.localhost` | Lê Chỉ Huy | Chỉ huy trưởng |
| `demo.kysu1@pm.localhost` | Nguyễn Kỹ Sư | Kỹ sư |
| `demo.kysu2@pm.localhost` | Phạm Giám Sát | Kỹ sư |
| `demo.totruong@pm.localhost` | Võ Tổ Trưởng | Tổ trưởng |

Để đăng nhập bằng một người dùng mẫu, quản trị vào Quản trị → Người dùng → chọn người → "Gửi liên kết đặt mật khẩu", rồi mở liên kết đó.

**Email (không bắt buộc).** Cảnh báo và tóm tắt luôn hiện trong ứng dụng, ở chuông thông báo và trang Cảnh báo. Muốn gửi cả email:
1. vào ERPNext Desk → Email Account, tạo tài khoản gửi đi;
2. bật "Enable Outgoing" và "Default Outgoing".

Khi chưa có tài khoản email, hộp "Tùy chọn thông báo" sẽ ghi rõ là hiện chỉ có thông báo trong ứng dụng.

## 2. Kịch bản demo trên dữ liệu mẫu (khoảng 20 phút)

Dự án **Nhà xưởng Tân Uyên – Bình Dương** (mã DEMO-XD01) được dựng từ BOQ mẫu. Ngày tháng tính lùi từ hôm nay nên lúc nào dựng cũng có cùng tình huống:

| Giai đoạn | Chế độ chuyển | Tình trạng |
|---|---|---|
| 1. PHẦN MÓNG | Tự động | 5 công tác đã làm xong theo nhật ký; 4 đã nghiệm thu, biên bản thứ 5 đang chờ chỉ huy trưởng duyệt |
| 2. PHẦN THÂN | Cần duyệt | Bê tông cột trễ 3 ngày, mới đạt 30%; cốt thép cột mới đạt 10% |
| 3. PHẦN HOÀN THIỆN | Thủ công | Chưa làm |

Nhật ký có đến hôm kia; hôm qua chưa có.

**Các bước:**

1. **Danh mục dự án** (menu Tổng quan → Danh mục dự án).
   - Các dự án mẫu đều chậm so với kế hoạch nên ở mức Đỏ (hoặc Vàng), kèm lý do: SPI, số ngày dự báo trễ.
   - Mỗi dự án có tiến độ so với kế hoạch, ngày dự báo xong, giai đoạn hiện tại, số cảnh báo đang mở, số việc quá hạn.
   - Bấm ô "Sức khỏe Đỏ" để lọc.
2. **Tổng quan của nhà xưởng.**
   - Ô trên cùng ghi sức khỏe dự án và lý do (SPI dưới 0,8: tiến độ đạt chưa tới 80% kế hoạch).
   - Ô giai đoạn: "Giai đoạn 1/3: PHẦN MÓNG", chuyển tự động, đang chờ "còn 1 công tác chưa nghiệm thu đủ khối lượng".
   - Danh sách cảnh báo đang mở:
     - quá hạn bê tông cột, đã leo thang bậc 1 lên chỉ huy trưởng;
     - chưa có nhật ký hôm qua;
     - cốt thép cột sắp đến hạn;
     - cốt thép cột có nguy cơ trễ.
3. **Quy tắc cảnh báo** (Quản trị → Quy tắc cảnh báo).
   - Mở quy tắc "Quá hạn": báo người chịu trách nhiệm chính và người thực hiện; sau 2 ngày báo chỉ huy trưởng, sau 5 ngày báo quản lý dự án.
   - Các quy tắc có sẵn sửa được (số ngày, người nhận, bậc leo thang, gửi email) và tắt được, nhưng không xóa được.
4. **Trên điện thoại, với vai chỉ huy trưởng.**
   - Trang Cảnh báo nhóm theo dự án; cảnh báo đã leo thang có nhãn "Leo thang bậc 1".
   - Bấm "Đã biết, đang xử lý" trên cảnh báo thiếu nhật ký, ghi chú nếu muốn: cảnh báo thôi leo thang.
   - Menu tài khoản → "Tùy chọn thông báo": giờ yên lặng (email chờ đến hết giờ), tóm tắt ngày và tuần, tắt từng loại cảnh báo.
5. **Duyệt biên bản cuối, giai đoạn tự chuyển.**
   - Chỉ huy trưởng mở tab Nghiệm thu, hoặc trang Biểu mẫu của dự án, chọn biên bản "đã nộp" của Bê tông móng rồi bấm Duyệt.
   - PHẦN MÓNG chuyển ngay sang PHẦN THÂN: ô giai đoạn ghi "Giai đoạn 2/3: PHẦN THÂN", chế độ Cần duyệt.
   - Hoạt động gần đây ghi "Chuyển từ giai đoạn PHẦN MÓNG sang PHẦN THÂN (tự động)"; quản lý dự án nhận thông báo.
6. **Tóm tắt.**
   - Mỗi sáng 7 giờ, mỗi người nhận một thông báo gộp: cảnh báo đang mở, việc quá hạn, việc sắp đến hạn, việc chờ nhận, biểu mẫu chờ duyệt.
   - Sáng thứ Hai, quản lý dự án nhận tóm tắt tuần của các dự án mình quản lý.

Kịch bản trình duyệt `scripts/e2e/ui/pilot_flow.mjs` chạy đúng các bước trên và chụp ảnh từng bước vào `scripts/e2e/ui/out/pilot/`.

### Vật tư, máy, chấm công (khoảng 10 phút)

Cũng trên nhà xưởng. Thủ kho mẫu là `demo.thukho@pm.localhost` (Đỗ Thủ Kho).

1. **Tab "Vật tư"** (thủ kho hoặc quản lý dự án):
   - kho công trường "Kho DEMO-XD01" có tồn kho, phiếu nhập và các phiếu cấp phát cho phần móng;
   - bảng "định mức so với thực tế" theo từng công tác có các cột: kế hoạch, đã cấp, trả lại, đã dùng, định mức của khối lượng đã làm, chênh lệch;
   - xi măng của bê tông móng đỏ và có cảnh báo "Vượt định mức vật tư": móng đã xong, đã dùng 14.450 kg trong khi định mức của khối lượng đã làm là 13.610 kg;
   - công tác chưa xong mà đã nhận nhiều hơn phần khối lượng đã làm cần thì có nhãn vàng "Cấp trước khối lượng" (vật tư đang chờ ở mặt bằng), không có cảnh báo.
2. **Kỹ sư, trên điện thoại** (tab Vật tư → "Đề xuất vật tư"):
   - chọn vật tư, công tác, số lượng rồi gửi;
   - tắt mạng vẫn gửi được: đề xuất nằm ở hàng đợi và tự gửi khi có mạng.
3. **Thủ kho cấp phát:**
   - ở mục "Đề xuất chờ cấp phát", bấm "Cấp phát" (các dòng đã điền sẵn) rồi xác nhận;
   - đề xuất chuyển sang đã cấp, số đã dùng và chênh lệch của công tác đổi ngay;
   - thiếu hàng thì báo "Không đủ tồn kho".
4. **Tab "Máy":**
   - máy đào (là tài sản trong ERPNext, đang ở công trường, sắp đến hạn bảo dưỡng), máy trộn, cần trục thuê;
   - kỹ sư ghi ca máy cho công tác trên điện thoại; nhiên liệu được so với định mức lít/ca.
5. **Tab "Chấm công":**
   - tổ trưởng chấm công tổ mình theo ngày, mỗi người một công tác;
   - chỉ huy trưởng xác nhận bảng đang chờ hoặc trả lại.
6. **Tab "Chi phí"** (quản lý dự án, kế toán dự án):
   - mỗi hạng mục, công tác có giá trị dự toán, giá trị đã thi công, chi phí vật tư, máy, nhân công, tổng thực tế và chênh lệch;
   - kỹ sư và tổ trưởng không xem được chi phí.

Kịch bản `scripts/e2e/ui/site_flow.mjs` chạy các bước 2, 3, 4 (ghi ca), 5 (xác nhận) và 6.

**Dựng lại dữ liệu mẫu nhà xưởng** sau khi demo (trong `docker/`):

```bash
docker compose exec backend bench --site pm.localhost execute pm_construction.pm_construction.setup.demo.down
```

```bash
docker compose exec backend bench --site pm.localhost execute pm_construction.pm_construction.setup.demo.up
```

### Khối lượng công việc, hiệu suất, nhiều dự án (khoảng 10 phút)

Trên cả hai dự án mẫu: tổ trưởng Võ Tổ Trưởng thực hiện phần thân ở nhà phố và phần kết cấu ở nhà xưởng.

1. **Trang "Khối lượng công việc"** (quản lý dự án `demo.quanly@pm.localhost`, hoặc quản trị):
   - mỗi người một dòng, mỗi tuần một ô: phần trăm = số ngày công cần / số ngày công có thể làm (ngày làm việc của lịch công ty, trừ nghỉ phép, bán thời gian);
   - trên 80 % là bận (vàng), trên 120 % là quá tải (đỏ); tổ trưởng quá tải nhiều tuần vì việc của hai dự án (việc đã trễ dồn phần còn lại vào các ngày tới);
   - mục "Xung đột giữa các dự án": tổ trưởng (người), và cần trục được hai dự án đặt trùng ngày (máy);
   - bấm một ô: danh sách việc trong tuần, mỗi việc bao nhiêu ngày công; việc ở dự án bạn không xem được hiện là "Dự án khác";
   - quản trị ghi kỳ nghỉ phép, bán thời gian ngay trong ô đó; Phạm Giám Sát đã có ba ngày nghỉ tuần sau.
2. **Trang "Hiệu suất"**:
   - theo người: việc xong, tỷ lệ đúng hạn, xong trễ, trễ trung bình, đang trễ, số lần báo tiến độ; bấm tên để xem từng dự án, các tuần trước và danh sách việc;
   - theo dự án; năng suất tổ đội (khối lượng nhật ký chia cho số công đã xác nhận trên cùng công tác);
   - kỹ sư chỉ thấy chính mình; tổ trưởng thấy tổ mình; quản lý, chỉ huy trưởng thấy mọi người trong dự án của họ.
3. **Danh mục dự án** thêm: tỷ lệ đúng hạn 4 tuần, số người quá tải tuần này (bấm để mở khối lượng công việc của dự án), xu hướng tiến độ 8 tuần, chi phí so với giá trị làm được và số công tác vượt định mức (lớp thi công; cột chi phí chỉ hiện cho người xem được chi phí).
4. **Tab "Máy" → "Lịch đặt máy"**: đặt máy cho một khoảng ngày; nếu dự án khác đã đặt cùng máy trùng ngày thì vẫn đặt được nhưng hiện "Trùng lịch".
5. **Chi tiết công việc → "Chiếm …% thời gian người làm"** (người lập kế hoạch): việc giám sát, theo dõi chỉ chiếm một phần ngày (ví dụ 25 %).

Kịch bản `scripts/e2e/ui/people_flow.mjs` chạy các bước 1–4.

### Ngân sách, rủi ro, phát sinh, báo cáo (khoảng 10 phút)

1. **Tab "Ngân sách"** (quản lý dự án, kế toán dự án):
   - tám ô EVM: ngân sách (BAC), giá trị kế hoạch (PV), giá trị thu được (EV), chi phí thực tế (AC), CPI, SPI, chi phí dự báo khi xong (EAC), chênh lệch khi xong (VAC);
   - ngân sách so với thực tế theo khoản mục và theo hạng mục;
   - "Điều chỉnh" tạo bản nháp từ ngân sách đang dùng; duyệt bản nháp thì bản cũ chuyển sang "Thay thế";
   - nhà phố chưa có chi phí thực tế vì dự án chỉ dùng lõi, chưa có timesheet; nhà xưởng có chi phí vật tư, máy, nhân công nên CPI có nghĩa;
   - kỹ sư, tổ trưởng không xem được tab này.
2. **Tab "Rủi ro, vấn đề"**:
   - ma trận 5 × 5 của các rủi ro đang mở; sổ rủi ro có người phụ trách, cách ứng phó, hạn;
   - "Đã xảy ra" đóng rủi ro và mở một vấn đề cần xử lý;
   - vấn đề quá hạn tô đỏ và có cảnh báo "Vấn đề quá hạn xử lý";
   - tổ trưởng và khách (chỉ thấy việc của mình) không xem được tab này.
3. **Tab "Phát sinh"**:
   - kỹ sư lập phát sinh (chi phí, số ngày, các công việc dời ngày) rồi gửi duyệt;
   - quản lý dự án duyệt hoặc từ chối (phải ghi lý do); người lập không tự duyệt;
   - duyệt thì chi phí cộng vào ngân sách đang dùng, công việc dời ngày cùng các việc phụ thuộc.
4. **Trang "Báo cáo"** (thanh bên, nhóm Tổng quan):
   - mười báo cáo theo nhóm Tiến độ, Nhân sự, Tài chính, Kiểm soát dự án, Thi công; mỗi báo cáo chỉ có dữ liệu trong phạm vi người xem;
   - xuất Excel, CSV, in, PDF có đầu trang công ty;
   - "Gửi theo lịch": hằng ngày, hằng tuần hoặc hằng tháng, PDF hoặc Excel. Mỗi người nhận nhận báo cáo theo quyền của chính họ; email chỉ đi khi hệ thống có tài khoản gửi email, thông báo trong ứng dụng luôn có. Quản lý dự án mẫu đã có lịch gửi "Tiến độ các dự án" sáng thứ Hai.
5. **Tab "Công việc"**: "Xuất MS Project" ra tệp XML mở được bằng MS Project; "Nhập MS Project" đọc tệp XML (cây, ngày, mốc, phụ thuộc, người phụ trách) với bước xem trước.
6. **Tab "Tổng quan" → "Kết thúc dự án"** (người sửa được dự án):
   - liệt kê những gì còn mở;
   - "Xuất hồ sơ dự án (ZIP)": lập ở nền, xong thì có thông báo kèm liên kết tải. Gói gồm manifest.json (mỗi mục có kích thước, SHA-256, nguồn), danh sách công việc, thành viên, rủi ro, vấn đề, phát sinh, ngân sách, tài liệu, biểu mẫu đã duyệt (PDF), nhật ký thi công, BOQ;
   - "Đóng dự án" (ghi kết luận) và "Mở lại".

Kịch bản `scripts/e2e/ui/control_flow.mjs` chạy các bước 1–6.

## 3. Đưa một công trình thật vào

1. **Người dùng và nhóm quyền** (Quản trị → Người dùng): tạo tài khoản; gán nhóm "Nhân viên"; giám đốc dùng nhóm có quyền xem mọi dự án.
2. **Dự án** (Dự án → Tạo dự án): tên, mã, ngày bắt đầu, ngày kết thúc hợp đồng; chọn quản lý dự án.
3. **Thành viên** (tab Thành viên): quản lý dự án, chỉ huy trưởng, kỹ sư, tổ trưởng. Vai trò quyết định ai thấy gì và ai nhận cảnh báo theo vai trò.
4. **BOQ** (tab BOQ):
   - nhập tệp Excel dự toán, xem trước, rồi duyệt;
   - hệ thống sinh cây hạng mục và công tác, và đổi cách tính tiến độ thành "Theo giá trị dự toán".
5. **Lịch** (tab Gantt hoặc Công việc):
   - đặt ngày cho công tác, vì BOQ không có ngày;
   - nối các công tác bằng phụ thuộc để có đường găng và dự báo đúng;
   - chụp baseline khi kế hoạch được chốt.
6. **Giao việc** (tab Công việc, hoặc chi tiết một công việc):
   - mỗi công tác có đúng một người chịu trách nhiệm chính, thêm người thực hiện nếu cần;
   - người nhận phải bấm "Nhận việc"; quá 2 ngày chưa nhận thì có cảnh báo.
7. **Chế độ chuyển giai đoạn** (Tổng quan → ô "Giai đoạn", ô chọn "Chuyển giai đoạn" dưới mỗi hạng mục cấp 1; cần quyền lập kế hoạch):
   - mặc định là Thủ công: quản lý dự án bấm chuyển khi sẵn sàng;
   - Tự động: chuyển ngay khi việc xong và mọi công tác đã nghiệm thu đủ; đổi sang Tự động lúc giai đoạn đã đủ điều kiện thì nó chuyển luôn;
   - Cần duyệt: đủ điều kiện thì quản lý dự án được báo và bấm "Duyệt chuyển giai đoạn".
8. **Vật tư:**
   - thêm thủ kho vào dự án với vai trò "Thủ kho" (được gán vai trò Stock User của ERPNext); bấm "Lập kho công trường" ở tab Vật tư;
   - vật tư (Item) tạo trong Desk của ERPNext, nhóm "Vật tư xây dựng";
   - định mức ở Danh mục → Định mức vật tư: mỗi mã hiệu của BOQ một định mức, gồm vật tư, hao phí cho một đơn vị và % hao hụt;
   - bấm "Tính lại kế hoạch" ở tab Vật tư sau khi nhập hoặc sửa định mức (duyệt BOQ cũng tự tính);
   - hàng về: thủ kho "Nhập kho" kèm đơn giá, hoặc phòng mua hàng lập PO, PR trong Desk về kho công trường.
9. **Máy và tổ đội:**
   - máy ở Danh mục → Máy thi công: máy sở hữu chọn tài sản ERPNext tương ứng, máy thuê chọn đơn vị cho thuê; đơn giá ca, định mức nhiên liệu;
   - tổ đội ở Danh mục → Đội, tổ (loại "Tổ đội", tổ trưởng); công nhân ở Danh mục → Công nhân (tổ, nghề, đơn giá công).
10. **Hằng ngày:**
   - kỹ sư ghi nhật ký kèm khối lượng (được cả khi mất mạng); chỉ huy trưởng xác nhận;
   - kỹ sư đề xuất vật tư, ghi ca máy; tổ trưởng chấm công; thủ kho cấp phát; chỉ huy trưởng xác nhận chấm công;
   - khi công tác xong, lập biên bản nghiệm thu công việc, rồi duyệt.

## 4. Quan sát và thu thập trong thí điểm

| Câu hỏi | Xem ở đâu |
|---|---|
| Cảnh báo có đúng người, đúng lúc không? Có quá nhiều không? | Trang Cảnh báo của từng người; Quản trị → Nhật ký hệ thống |
| Ngưỡng sức khỏe có hợp lý không? | Thiết lập hệ thống: trễ quá bao nhiêu ngày thì Đỏ (mặc định 3, hoặc 10% thời lượng), mấy ngày không cập nhật là đình trệ (5), tốt lên phải giữ mấy ngày (3) |
| Bậc leo thang có hợp với cách công ty xử lý không? | Quy tắc cảnh báo: số ngày và người nhận từng bậc |
| Nhật ký có được ghi đều không? | Cảnh báo "Thiếu nhật ký thi công"; tab Nhật ký |
| Người ở công trường có dùng được trên điện thoại không? | Hàng đợi gửi (khi mất mạng); góp ý trực tiếp |
| Chuyển giai đoạn có đúng quy trình không? | Ô giai đoạn ở Tổng quan; Hoạt động gần đây |
| Định mức có sát thực tế không? Hao hụt thật là bao nhiêu? | Tab Vật tư: chênh lệch theo công tác; cảnh báo "Vượt định mức vật tư" |
| Chi phí thực tế có khớp sổ kế toán không? | Tab Chi phí so với báo cáo của ERPNext (theo dự án) |

Ghi lại mỗi tuần: số cảnh báo theo loại, số cảnh báo được xác nhận, số cảnh báo phải leo thang, những cảnh báo người dùng thấy thừa.

## 5. Giới hạn hiện tại (sẽ làm ở các phase sau)

- **Mua hàng** (PO, PR, hóa đơn) làm trong Desk của ERPNext; chưa có màn hình riêng. Danh mục vật tư (Item) cũng tạo trong Desk.
- **Giờ tăng ca** được ghi trong chấm công nhưng chưa tính tiền.
- **Khối lượng công việc** chỉ tính việc có ngày kế hoạch, giao cho người (không tính việc giao cho cả đội); việc đã trễ dồn phần còn lại vào các ngày làm việc từ hôm nay. Lịch nghỉ là lịch của công ty, chưa có lịch riêng từng người ngoài các kỳ nghỉ phép, bán thời gian.
- **Hiệu suất** tính trên việc được giao (chịu trách nhiệm, thực hiện); ảnh chụp tuần ghi lại số liệu mỗi sáng thứ Hai, nên xu hướng chỉ có từ khi hệ thống chạy.
- **Chi phí thực tế của dự án chỉ dùng lõi** lấy từ Timesheet của ERPNext (chi phí nhân công); dữ liệu mẫu nhà phố chưa có timesheet nên chưa có AC. Mua hàng, hóa đơn chưa được tính vào AC.
- **Báo cáo gửi theo lịch** đi vào phút thứ 5 của giờ đã chọn, theo giờ của hệ thống; email cần tài khoản gửi email của Frappe.
- **MS Project**: chỉ trao đổi tệp XML (không đọc tệp .mpp); lịch làm việc, tài nguyên ngoài thành viên dự án, chi phí trong tệp không được nhập.
- **Hồ sơ dự án** là tệp ZIP giữ trong hệ thống; chưa có cầu nối tự gửi sang hệ thống lưu trữ (điểm mở rộng `project_close_handlers` đã có).
- **Kênh nhận:** cảnh báo chỉ đi qua thông báo trong ứng dụng và email; chưa có Zalo, SMS.
- **Lịch chạy:** cảnh báo được đánh giá mỗi sáng 6 giờ, leo thang mỗi giờ. Một việc vừa quá hạn trong ngày sẽ được báo vào sáng hôm sau.
- **Giờ yên lặng** chỉ áp dụng cho email; thông báo trong ứng dụng luôn đến.
- **Giai đoạn** là các hạng mục cấp 1 của cây công việc, đi theo thứ tự của cây; chưa có giai đoạn song song.
