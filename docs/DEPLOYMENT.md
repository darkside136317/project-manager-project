# Triển khai lên máy chủ

Tài liệu này dành cho người cài hệ thống cho doanh nghiệp: một máy chủ Linux, một tên miền, chạy lâu dài. Muốn chạy thử trên máy cá nhân thì dùng `scripts/bootstrap` như trong [README](../README.md).

Sao lưu và khôi phục: [SAO_LUU_KHOI_PHUC.md](SAO_LUU_KHOI_PHUC.md). Hướng dẫn cho người dùng: [HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md).

## 1. Máy chủ

| | Tối thiểu | Khuyến nghị (50 dự án đang chạy, 500 người) |
|---|---|---|
| CPU | 4 nhân | 8 nhân |
| RAM | 8 GB | 16 GB |
| Ổ đĩa | 60 GB SSD | 200 GB SSD (ảnh, tài liệu tăng theo thời gian) |
| Hệ điều hành | Linux x86_64 (Ubuntu 22.04/24.04, Debian 12) | |
| Phần mềm | Docker Engine 24+ có Compose v2, `git`, `python3`, `curl` | |

Còn cần:
- một **tên miền** (ví dụ `duan.congty.vn`) trỏ về máy chủ;
- cổng **80 và 443** mở ra Internet. Các cổng khác không cần mở.

## 2. Chuẩn bị

```bash
git clone https://github.com/darkside136317/project-manager-project.git
cd project-manager-project
cp docker/.env.prod.example docker/.env.prod
chmod 600 docker/.env.prod
```

Sửa `docker/.env.prod`:

| Biến | Điền |
|---|---|
| `FRAPPE_SITE_NAME` | Tên miền, ví dụ `duan.congty.vn` |
| `PUBLIC_URL` | `https://` + tên miền |
| `COMPANY_NAME`, `COMPANY_ABBR` | Tên công ty và viết tắt (ERPNext tạo công ty, năm tài chính, lịch nghỉ có ngày lễ Việt Nam theo các biến này). **Sửa trước lần triển khai đầu tiên.** |
| `HTTP_PUBLISH_PORT` | Mặc định `127.0.0.1:8890`: nginx của hệ thống chỉ nghe trong máy chủ, reverse proxy ở mục 4 đi qua đây |
| `COMPOSE_PROJECT_NAME`, `DATA_VOLUME_PREFIX` | Mặc định `pmprod`; đổi khi chạy nhiều bản trên cùng máy |
| `DATA_ROOT` | Không bắt buộc: thư mục trên máy chủ để giữ dữ liệu (ví dụ `/srv/pm-data`). Để trống thì dữ liệu nằm trong volume của Docker |
| `PM_IMAGE`, `PM_IMAGE_TAG` | Không bắt buộc: dùng image CI đã build (`ghcr.io/<chủ repo>/pm-custom`, tag là phiên bản ERPNext, `latest` hoặc `sha-<commit>`). Để trống thì build trên máy chủ (lần đầu mất khoảng 10–15 phút) |
| Các mật khẩu | **Để trống**: script tự sinh, mỗi cái 48 ký tự ngẫu nhiên |

## 3. Triển khai

```bash
scripts/deploy_prod.sh
```

Script làm lần lượt:
1. Sinh các mật khẩu còn trống.
2. Kiểm `docker/.env.prod` bằng `scripts/validate_prod_env.py`. Script dừng nếu:
   - tên miền là `localhost` hoặc `*.local`;
   - `PUBLIC_URL` không phải `https://<tên miền>`;
   - cổng mở ra ngoài thay vì `127.0.0.1`;
   - mật khẩu yếu hoặc trùng nhau;
   - prod dùng chung volume hay mật khẩu với bản dev;
   - thiếu tên công ty.
3. Build image (hoặc kéo image CI), build MinIO từ mã nguồn đã ghim phiên bản.
4. Khởi động MariaDB, Redis, Meilisearch, MinIO; tạo bucket và tài khoản riêng của ứng dụng trên MinIO.
5. Tạo site và cài ERPNext cùng ba app (`project_manager`, `pm_construction`, `pm_archive`), chạy setup wizard. Site đã có thì cài thêm app còn thiếu rồi migrate.
6. Khởi động toàn bộ dịch vụ, chờ site trả lời.

Chạy lại script bất cứ lúc nào cũng an toàn: dữ liệu và mật khẩu được giữ nguyên.

Hệ thống chạy dưới dạng các container Docker, khởi động lại cùng máy chủ (`restart: always`) và có giới hạn bộ nhớ (biến `*_MEMORY`). Chỉ nginx được mở, và chỉ ở `127.0.0.1`. MariaDB, Redis, Meilisearch, MinIO chỉ nằm trong mạng nội bộ của Docker.

## 4. HTTPS (reverse proxy)

Hệ thống không tự giữ chứng chỉ. Một reverse proxy trên máy chủ nhận HTTPS và chuyển về `127.0.0.1:8890`. Proxy cần:
- chuyển cả websocket ở `/socket.io` (thông báo, trao đổi cập nhật ngay);
- cho tệp lên tới 200 MB;
- giữ `Host` và gửi `X-Forwarded-For`, `X-Forwarded-Proto`.

**Caddy** tự lấy và gia hạn chứng chỉ Let's Encrypt. Tệp `/etc/caddy/Caddyfile`:

```
duan.congty.vn {
    encode gzip
    request_body {
        max_size 200MB
    }
    reverse_proxy 127.0.0.1:8890
}
```

**nginx**, chứng chỉ lấy bằng `certbot --nginx -d duan.congty.vn`:

```nginx
server {
    listen 443 ssl http2;
    server_name duan.congty.vn;
    # ssl_certificate ... do certbot điền

    client_max_body_size 200m;
    proxy_read_timeout 120s;

    location / {
        proxy_pass http://127.0.0.1:8890;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
server {
    listen 80;
    server_name duan.congty.vn;
    return 301 https://$host$request_uri;
}
```

Mở `https://duan.congty.vn/pm`, đăng nhập `Administrator` bằng `ADMIN_PASSWORD` trong `docker/.env.prod`.

Ứng dụng trên điện thoại (PWA, hàng đợi gửi lại khi mất mạng) chỉ hoạt động qua HTTPS.

## 5. Sau khi triển khai

1. **Người dùng, nhóm quyền:** màn Quản trị → Người dùng, Phân quyền. Mỗi người một tài khoản và đặt mật khẩu qua liên kết; không dùng chung tài khoản Administrator.
2. **Email:** trong Desk (`/desk`) tạo một Email Account gửi đi mặc định (SMTP của công ty). Khi có, cảnh báo và báo cáo gửi theo lịch đi cả qua email; khi chưa có, chỉ có thông báo trong ứng dụng.
3. **Sao lưu hằng ngày:** thêm vào crontab của máy chủ (chi tiết và cách giữ bản ngoài máy: [SAO_LUU_KHOI_PHUC.md](SAO_LUU_KHOI_PHUC.md)):
   ```
   30 1 * * * cd /srv/project-manager-project && scripts/backup.sh --prod >> /var/log/pm-backup.log 2>&1
   ```
4. **Giám sát:** màn Quản trị → Giám sát hệ thống: tình trạng cơ sở dữ liệu, Redis, Meilisearch, MinIO, hàng đợi.
5. **Bảo mật đăng nhập** (Desk → System Settings). Mặc định đã có:
   - chính sách mật khẩu (độ mạnh tối thiểu 2);
   - khóa 60 giây sau 10 lần đăng nhập sai;
   - phiên đăng nhập 7 ngày.
   
   Có thể bật xác thực hai lớp cho các vai trò quản trị.

## 6. Vận hành

Mọi lệnh `docker compose` cho bản prod đi qua `scripts/prod_compose.py`. Script đọc `docker/.env.prod`, kiểm nó, rồi thêm các overlay prod:

```bash
python3 scripts/prod_compose.py ps                      # các dịch vụ
python3 scripts/prod_compose.py logs -f --tail=100 backend
python3 scripts/prod_compose.py restart backend queue-pm queue-short queue-long scheduler
python3 scripts/prod_compose.py exec backend bench --site duan.congty.vn console
```

Các job nền chạy theo giờ của máy chủ:

| Giờ | Việc |
|---|---|
| Mỗi 5 phút | Cộng dồn tiến độ còn sót |
| Mỗi giờ (phút 0) | Leo thang cảnh báo |
| Mỗi giờ (phút 5) | Gửi báo cáo theo lịch |
| 01:30 thứ Hai | Ảnh chụp hiệu suất tuần trước |
| 06:00 | Đánh giá các quy tắc cảnh báo |
| 07:00 | Tóm tắt ngày; thứ Hai thêm tóm tắt tuần |
| Hằng đêm | Dự báo, sức khỏe, đối soát cộng dồn |

## 7. Nâng cấp

```bash
git pull
scripts/deploy_prod.sh --backup
```

Một app mới của hệ thống (ví dụ `pm_archive`, lưu trữ hồ sơ, từ M12) được cài lên site đang chạy ở bước này. Muốn bỏ một lớp thì đặt `PM_INSTALL_APPS` trong `docker/.env.prod` (mặc định `erpnext project_manager pm_construction pm_archive`) trước lần triển khai đầu; lớp đã cài thì không tự gỡ.

`--backup` sao lưu đầy đủ trước (mục 3 của [SAO_LUU_KHOI_PHUC.md](SAO_LUU_KHOI_PHUC.md)), rồi build image mới, migrate và khởi động lại. Khi dùng image của CI, đổi `PM_IMAGE_TAG` sang tag mới (ví dụ `sha-5483684`).

**Quay lui:**
1. `git checkout <phiên bản trước>`, hoặc đặt lại `PM_IMAGE_TAG` cũ;
2. `scripts/deploy_prod.sh`;
3. nếu migrate của bản mới đã đổi dữ liệu thì khôi phục bản sao lưu vừa lấy (`scripts/restore.sh --prod <thư mục>`).

**Nâng cấp ERPNext** (đổi `ERPNEXT_VERSION`) cần thận trọng hơn, vì hệ thống can thiệp vào Task, Project, Timesheet của ERPNext (kế hoạch, mục 4.2):
1. đọc thay đổi của `erpnext/projects/doctype/task/task.py`, `project.py`, `timesheet.py` và `frappe/utils/nestedset.py` giữa hai phiên bản;
2. trên máy dev: đổi `ERPNEXT_VERSION` trong `docker/.env`, `scripts/bootstrap.sh`, chạy toàn bộ test (`run-tests --app project_manager`, `--app pm_construction`; `test_task_mixin` kiểm các method mà hệ thống ghi đè);
3. khôi phục một bản sao lưu của prod lên máy thử, migrate, chạy các kịch bản trình duyệt;
4. chỉ khi tất cả xanh mới đổi trên prod (kèm `--backup`).

## 8. Diễn tập trên máy thử

Muốn thử toàn bộ quy trình prod mà chưa có tên miền thật: dùng tên `*.test`, `PUBLIC_URL=http://<tên>`, và chạy với biến môi trường `PM_REHEARSAL=1`:

```bash
export PM_REHEARSAL=1
scripts/deploy_prod.sh
```

Biến này cần cho mọi lệnh của bản diễn tập (`prod_compose.py`, `backup.sh --prod`, `restore.sh --prod`): thiếu nó, trình kiểm từ chối tên `*.test` như với bản thật. Trình kiểm vẫn bắt các lỗi khác. Trong M11, quy trình này đã được diễn tập trên một máy Windows (Git Bash, Docker Desktop): kết quả ở [nhật ký M11](build-log/12-m11-hardening-trien-khai.md).
