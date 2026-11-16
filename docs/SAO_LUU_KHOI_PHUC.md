# Sao lưu và khôi phục

## 1. Dữ liệu nằm ở đâu

| Phần | Nơi lưu | Có trong bản sao lưu |
|---|---|---|
| Dữ liệu nghiệp vụ (dự án, công việc, trao đổi, biểu mẫu, ngân sách, kho…) | MariaDB | Có: `*-database.sql.gz` |
| Tệp đính kèm của Frappe: biểu mẫu đã duyệt (PDF), hồ sơ dự án (ZIP), tệp tải vào Desk | Thư mục `sites` | Có: `*-files.tar`, `*-private-files.tar` |
| Cấu hình của site, gồm **khóa mã hóa** (giải mã mật khẩu SMTP, API key đã lưu) | `site_config.json` | Có: `*-site_config_backup.json` |
| Ảnh hiện trường, tài liệu dự án | MinIO (bucket `pm-files`) | Có: thư mục `minio/` |
| Chỉ mục tìm kiếm | Meilisearch | Không: dựng lại từ dữ liệu khi khôi phục |
| Hàng đợi, bộ nhớ đệm | Redis | Không: không cần |
| Các mật khẩu của hệ thống (CSDL, MinIO, Meilisearch, Administrator lúc cài) | `docker/.env.prod` | **Không**: giữ tệp này riêng, ở nơi an toàn |

## 2. Lấy bản sao lưu

```bash
scripts/backup.sh --prod                 # vào backups/<site>-<ngày-giờ>/
scripts/backup.sh --prod /mnt/backup/pm  # hoặc vào một thư mục chọn trước
```

Bỏ `--prod` khi sao lưu bản chạy thử trên máy cá nhân (dùng `docker/.env`).

Mỗi bản sao lưu là một thư mục gồm:
- các tệp của Frappe;
- thư mục `minio/`;
- `MANIFEST.txt`: tên site, thời điểm, phiên bản mã, số đối tượng MinIO, SHA-256 của từng tệp.

`MANIFEST.txt` được ghi sau cùng: thư mục không có nó là bản sao lưu chưa xong, và `restore.sh` từ chối nó. Khi sao lưu thất bại, script xóa thư mục nó vừa tạo. Nếu thư mục đích đã có từ trước (do bạn chọn), script giữ nguyên và báo thư mục đó chưa đầy đủ.

Hệ thống vẫn chạy trong lúc sao lưu. Các tệp được sao lưu ngay khi tạo ra; dữ liệu của MariaDB lấy được nhất quán nhờ `mysqldump --single-transaction` của Frappe.

## 3. Lịch sao lưu và giữ bản ngoài máy

Trên máy chủ (`crontab -e` của người chạy Docker):

```
# 01:30 mỗi ngày: sao lưu đầy đủ
30 1 * * * cd /srv/project-manager-project && scripts/backup.sh --prod /srv/backups/pm/$(date +\%F) >> /var/log/pm-backup.log 2>&1
# giữ 14 ngày trên máy
30 3 * * * find /srv/backups/pm -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

**Bản sao lưu phải có ít nhất một bản nằm ngoài máy chủ**, vì đĩa hoặc máy hỏng thì mất cả hai. Ví dụ:
- đồng bộ thư mục sao lưu sang ổ NAS, hoặc dịch vụ lưu trữ đối tượng bằng `rclone` hay `rsync` (mỗi ngày, sau giờ sao lưu);
- mã hóa trước khi gửi ra ngoài:
  ```
  tar -C /srv/backups/pm -cf - 2026-11-16 | age -r <khóa công khai> > pm-2026-11-16.tar.age
  ```
- giữ `docker/.env.prod` cùng chỗ với khóa giải mã, không để chung với bản sao lưu.

Thời gian và dung lượng tham khảo (mục 6):
- dữ liệu mẫu (2 dự án): sao lưu 10–18 giây, 2–4 MB; khôi phục khoảng 1 phút;
- ảnh và tài liệu chiếm phần lớn dung lượng theo thời gian.

## 4. Khôi phục

Áp dụng cho cả máy cũ (quay lui) lẫn **máy khác** (máy hỏng, chuyển máy chủ).

1. **Trên máy đích**, cài hệ thống mới với **cùng tên site** (`FRAPPE_SITE_NAME`). Khóa của ảnh và tài liệu trên MinIO gắn với tên site, nên `restore.sh` từ chối bản sao lưu của site khác. Cài bằng:
   - prod: `scripts/deploy_prod.sh`, theo [DEPLOYMENT.md](DEPLOYMENT.md);
   - máy thử: `scripts/bootstrap.sh`.
   
   Mật khẩu CSDL và MinIO của máy đích có thể khác máy cũ.
2. Chép thư mục sao lưu sang máy đích, rồi:
   ```bash
   scripts/restore.sh --prod /đường/dẫn/<site>-<ngày-giờ>
   ```
   Script làm lần lượt:
   - kiểm SHA-256 theo `MANIFEST.txt`;
   - khôi phục CSDL và tệp;
   - đặt lại khóa mã hóa của site cũ;
   - chép các đối tượng MinIO vào bucket;
   - migrate, dựng lại chỉ mục tìm kiếm, khởi động lại các dịch vụ.
3. Đăng nhập bằng tài khoản của **dữ liệu cũ**: mật khẩu Administrator lúc này là mật khẩu trên máy cũ, không phải `ADMIN_PASSWORD` của máy đích. Muốn đặt lại:
   ```bash
   python3 scripts/prod_compose.py exec backend bench --site <site> set-admin-password <mật khẩu mới>
   ```
4. Kiểm tra:
   - màn Quản trị → Giám sát hệ thống;
   - mở một dự án: tiến độ, trao đổi;
   - một ảnh hiện trường, một tài liệu tải về được;
   - tìm kiếm trong trao đổi có kết quả.

Khôi phục **ghi đè** dữ liệu đang có trên site đích. Muốn giữ dữ liệu hiện tại thì sao lưu nó trước.

## 5. Mức chấp nhận

- **Mất dữ liệu tối đa (RPO):** từ lần sao lưu gần nhất, tức tối đa một ngày với lịch ở mục 3. Cần ít hơn thì sao lưu thường hơn (ví dụ 4 giờ một lần): mỗi lần là một bản đầy đủ.
- **Thời gian khôi phục (RTO):** cài hệ thống mới (15–30 phút, phần lớn là build image; dùng image CI thì nhanh hơn) cộng thời gian chép và khôi phục dữ liệu (mục 6).

## 6. Diễn tập

Diễn tập M11 (2026-11-16): khôi phục từ bản prod thử sang một stack khác, mật khẩu khác, cùng tên site.

| Bước | Kết quả |
|---|---|
| Sao lưu (dữ liệu mẫu, 2 dự án, 6 đối tượng MinIO) | 10,5 giây, 2,1 MB |
| Cài hệ thống mới (image có sẵn) | 2 phút 45 giây |
| Khôi phục | 65 giây |
| So với nguồn: số dòng của 19 loại dữ liệu, tiến độ dự án, từng đối tượng MinIO (theo SHA-256), giá trị mã hóa, chỉ mục tìm kiếm | Trùng khớp cả 28 dữ kiện |
| Đăng nhập | Bằng mật khẩu Administrator của máy cũ; đặt lại được (mục 4, bước 3) |
| Kịch bản trình duyệt trao đổi (ảnh, tệp, tìm kiếm) trên bản khôi phục | 27/27 |

Script cũng được thử ở đường lỗi:
- sao lưu khi hệ thống đang dừng thì báo lỗi và xóa thư mục dở dang;
- khôi phục từ thư mục không có manifest, hay bản sao lưu của site khác, thì bị từ chối trước khi đụng vào dữ liệu.

Chi tiết: [nhật ký M11](build-log/12-m11-hardening-trien-khai.md#6-diễn-tập-sao-lưu-và-khôi-phục). Nên diễn tập lại mỗi quý, và sau mỗi lần nâng cấp lớn.
