#!/usr/bin/env bash
# =============================================================================
# One command from a fresh clone to a running site (Linux, macOS, Git Bash on Windows).
# Windows PowerShell: scripts/bootstrap.ps1 does the same.
#
#   scripts/bootstrap.sh           build, create the site if needed, start everything
#   scripts/bootstrap.sh --dev     same, with the dev overlay (source mounted, live reload)
#   scripts/bootstrap.sh --local   back to the built image only
#
# Safe to run again: existing secrets, site and data are kept; the site is migrated.
# =============================================================================
set -euo pipefail

mode=""
for arg in "$@"; do
  case "$arg" in
    --dev) mode=dev ;;
    --local) mode=local ;;
    -h|--help) sed -n '3,10p' "$0"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $arg (xem --help)" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/docker"
export MSYS_NO_PATHCONV=1  # Git Bash: pass container paths through unchanged
ONE_SHOTS='^(configurator|create-site|setup-site)$'

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'LỖI: %s\n' "$*" >&2; exit 1; }
get_value() { { grep -E "^$1=" .env || true; } | tail -n 1 | cut -d= -f2-; }
set_value() {
  local tmp
  tmp="$(mktemp)"
  awk -v key="$1" -v value="$2" '
    index($0, key "=") == 1 { print key "=" value; done = 1; next }
    { print }
    END { if (!done) print key "=" value }' .env > "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
}
random_secret() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

step "Kiểm tra Docker"
command -v docker >/dev/null 2>&1 || die "Chưa cài Docker (Docker Desktop hoặc Docker Engine 24+)."
docker info >/dev/null 2>&1 || die "Docker chưa chạy. Mở Docker Desktop / khởi động dịch vụ docker rồi chạy lại."
docker compose version >/dev/null 2>&1 || die "Cần Docker Compose v2 (lệnh 'docker compose')."
memory="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
if [ "${memory:-0}" -lt $((7 * 1024 * 1024 * 1024)) ]; then
  echo "Cảnh báo: Docker đang có $((memory / 1024 / 1024)) MB RAM; nên cấp ít nhất 8 GB."
fi

step "Cấu hình docker/.env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Đã tạo docker/.env từ docker/.env.example"
fi
chmod 600 .env 2>/dev/null || true
for key in ADMIN_PASSWORD MARIADB_ROOT_PASSWORD MEILISEARCH_MASTER_KEY; do
  if [ -z "$(get_value "$key")" ]; then
    set_value "$key" "$(random_secret)"
    echo "Đã sinh $key"
  fi
done
case "$mode" in
  dev) set_value COMPOSE_FILE docker-compose.yml,docker-compose.dev.yml ;;
  local) set_value COMPOSE_FILE docker-compose.yml,docker-compose.local.yml ;;
esac
echo "Overlay: $(get_value COMPOSE_FILE)"

step "Build image (lần đầu mất vài phút)"
docker compose build

step "Khởi động cơ sở dữ liệu, Redis, Meilisearch"
docker compose up -d db redis-cache redis-queue meilisearch

step "Cấu hình, tạo site (nếu chưa có), setup wizard, migrate"
docker compose run --rm --no-deps configurator
docker compose run --rm --no-deps create-site
docker compose run --rm --no-deps setup-site

step "Khởi động toàn bộ dịch vụ"
# shellcheck disable=SC2046  # one service name per word
docker compose up -d --no-deps --remove-orphans $(docker compose config --services | grep -vE "$ONE_SHOTS")

port="$(get_value HTTP_PUBLISH_PORT)"
url="http://localhost:${port:-8890}"
step "Chờ $url phản hồi"
if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 60); do
    if curl -fsS "$url/api/method/ping" >/dev/null 2>&1; then ready=1; break; fi
    sleep 5
  done
  [ "${ready:-0}" = 1 ] || die "Site chưa phản hồi sau 5 phút. Xem log: cd docker && docker compose logs --tail=100"
else
  echo "Không có curl: bỏ qua bước chờ."
fi

cat <<EOF

Xong. Hệ thống đang chạy:
  Quản lý dự án : $url/pm
  ERPNext (Desk): $url/desk
  Tài khoản     : Administrator
  Mật khẩu      : biến ADMIN_PASSWORD trong docker/.env
Dừng: cd docker && docker compose stop    ·    Chạy lại: scripts/bootstrap.sh
EOF
