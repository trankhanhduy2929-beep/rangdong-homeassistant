# Báo cáo triển khai license — 05/09/2026

## Phân tích source ban đầu

Baseline Git: `44b5af5` (bộ APK tích hợp sẵn đã được người dùng xác nhận chạy tốt).
Add-on dùng aiohttp Ingress, xác minh quyền quản trị/CSRF; controller gọi worker
Java một lần, kiểm tra key rồi chuyển qua Supervisor đến bridge HA. Custom tạo
config entry cho từng thiết bị LAN; coordinator/switch/sensor điều khiển độc lập.

Các điểm mở rộng phù hợp là Ingress API trước cloud login, API bridge có xác thực
và config/options flow HA. Không cần sửa worker hoặc giao thức thiết bị để thêm
license. Website/payment service tách thành dự án Next.js độc lập.

## Những phần giữ nguyên

Không thay đổi `local.py`, `coordinator.py`, `switch.py`, `sensor.py`, `cloud.py`,
`cloud_assets.py`, Java worker/protocol hoặc APK đã ghim. Giữ nguyên dữ liệu config
entry thiết bị. Thêm view license không thay đổi payload key-import đang dùng.
Không cài bản này lên Home Assistant của người dùng, không chạy thanh toán thật.

## Phần bổ sung

- `license-server/`: schema PostgreSQL và D1, auth email OTP, PayOS checkout/webhook,
  dashboard/admin, mã hóa key, binding installation/slot và lease Ed25519.
- `custom_components/rangdong_smart/licensing.py`: danh tính cài đặt private,
  xác minh signed lease và gọi server; view HA chỉ dành cho admin.
- `config_flow.py`: license ở bước setup mới và phần Options; không đưa key vào
  config entry thiết bị, không thêm việc phụ thuộc mạng vào điều khiển LAN.
- Add-on `licensing.py`: UUID bền vững, gửi qua bridge HA. UI/API Android/root và
  upload APK đã gỡ; giữ cloud login, danh sách và xóa key bridge.
- `tools/`: cấu hình public origin/public key và ZIP an toàn. Bản local add-on
  loại trường image để Supervisor build source thay vì kéo tag chưa phát hành.

## Kết quả kiểm thử

- **69 pytest** integration/helper: đạt. Bao gồm hồi quy code cũ, signed lease,
  sai installation/component/thời hạn, offline grace, revoke không dùng cache,
  compatibility không gọi server, gate license trước cloud, CSRF và API đã gỡ.
- **27 Node tests: đạt**, gồm PostgreSQL/PGlite và D1/SQLite + Worker gateway: kiểm tra schema và transaction, OTP/replay,
  quyền admin/CSRF, webhook giả/trùng/sai số tiền, xác nhận lại provider, giá đơn
  từ server, request idempotent, cấp key một lần, rollback, hai slot cùng HA,
  bind khác HA bị từ chối, reset đổi key và audit.
- Email/mật khẩu không cần OTP; scrypt + salt, chặn đăng ký email admin và
  dùng bảng role riêng. Trial cấp một lần/tài khoản và installation, kể cả race,
  reset/thu hồi/hết hạn; gói tháng 50.000đ/30 ngày từ dữ liệu server.
- TypeScript check, Next.js production build: đạt. HTTP production smoke cho
  trang chủ/dashboard/admin: 200 và có security headers.
- Ruff lint, formatter trên file thay đổi, cú pháp JavaScript add-on: đạt.
- `npm audit --omit=dev`: 0 vulnerability được registry báo tại thời điểm chạy.
- Test ZIP source giải nén không có `.git`, chạy configure với public key thử,
  đóng ZIP `licensed` và kiểm tra bỏ trường image ở bản local: đạt.
- Scan source/ZIP không có tài khoản thử, key thiết bị, secret APK trích xuất,
  private key server, file môi trường thật hoặc thư mục build/cache.

## Phạm vi chưa kiểm chứng thực tế

Đã deploy server Vercel, Cloudflare Worker/D1 bằng phiên đăng nhập được CLI làm
mới; PayOS xác nhận webhook production thành công. Live smoke trang chủ,
dashboard/admin đạt 200, dashboard API chưa đăng nhập trả 401, webhook giả trả
400. D1 live rollback không để lại user thử nghiệm. Đăng ký/password, quyền admin,
trial hai slot và chặn trial tài khoản khác đã kiểm tra trực tiếp trên production.
PayOS tạo QR tháng 50.000đ và hủy/đối soát thành công, không chuyển tiền. Automated
payment/email dùng mock; cần kiểm tra giao dịch tiền thật trước mở bán.
Chi tiết trong `DEPLOY_STATUS_VI.md`.
Máy phát triển không có Docker/Podman, không build image add-on mới tại đây;
ZIP local đủ source để Supervisor build, CI đã có bước build khi anh tự push.

Gói `licensed` đã gắn public URL/key production, `ENFORCE=True`. Gói `setup` cũ
là bản compatibility, không dùng nhầm để phát hành thương mại.
License chặn thiết lập mới/lấy key mới, không ngắt điều khiển thiết bị đang chạy.
Không thể chống clone nguyên private storage hoặc sửa Python source tuyệt đối;
chi tiết và độ trễ thu hồi offline có trong `LICENSE_DEPLOY_VI.md`.

Không commit hoặc push GitHub trong lượt triển khai này theo yêu cầu người dùng.

## Cập nhật website: mật khẩu và mobile

Thêm endpoint `POST /api/auth/password` yêu cầu session, đúng origin, mật khẩu cũ,
xác nhận mật khẩu mới và rate limit. Update credential, thu hồi session và cấp
cookie mới nguyên tử; compare-and-swap chống hai lần đổi đồng thời. Audit không
chứa mật khẩu. Test kiểm tra session cũ bị từ chối và key/trial giữ nguyên.

Dashboard đọc dữ liệu D1 qua ba request gateway thay vì bảy (gồm rate limit/session);
admin qua bốn thay vì chín. Truy vấn dữ liệu được gom batch, không giảm kiểm tra
xác thực và không cache dữ liệu riêng. UI ngừng polling khi tab ẩn/không có đơn chờ,
không lặp request lấy gói khi phân trang, hủy response lỗi thời.

Test trình duyệt `license-server/tests/ui.browser.mjs` dùng Playwright cài riêng
(không tăng dependency website). `BROWSER_BASE_URL` trỏ server Next đang chạy;
`PLAYWRIGHT_MODULE`/`BROWSER_EXECUTABLE_PATH` tùy chọn khi dùng bản cài ở vị trí khác.
API được mock trong test UI, không sửa tài khoản hoặc thanh toán thật. Kiểm tra
không tràn ngang ở 320/390/768/1280px, form mật khẩu, bảng admin, polling và draft.

Đã chạy UI test trên tài nguyên production sau deploy (API được mock). Kiểm tra
API thật riêng bằng tài khoản test: đổi mật khẩu, mất hiệu lực cả hai session cũ,
giữ nguyên license/trial/đơn và đăng nhập mật khẩu mới thành công. Không tác động
mật khẩu admin hoặc khách hàng. Đo dashboard bốn lượt trước/sau từ cùng máy:
2216/2043/2046/2048 ms → 1071/1075/1075/1089 ms; kết quả phụ thuộc đường mạng.
