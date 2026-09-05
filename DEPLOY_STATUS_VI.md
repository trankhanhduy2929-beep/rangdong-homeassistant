# Trạng thái triển khai ngày 05/09/2026

## Đã triển khai

- Website: `https://rangdong-license-portal.vercel.app`.
- Tài khoản/đơn/key: `/dashboard`. Trang quản trị riêng: `/admin`.
- Database D1 `rangdong-license-production`, Worker `rangdong-license-db`.
- Khách đăng ký email + mật khẩu, không cần OTP/Resend; số điện thoại tùy chọn.
- PayOS đã xác nhận webhook production `/api/payos/webhook`.

| Gói | Giá | Bắt đầu / thời hạn |
| --- | --- | --- |
| Dùng thử | Miễn phí | 24 giờ từ lần kích hoạt đầu tiên |
| 1 tháng | 50.000đ | 30 ngày từ xác nhận thanh toán |
| Vĩnh viễn | 200.000đ | Không có ngày hết hạn |

Trial chỉ nhận một key/tài khoản, một lượt/installation. Dùng chung key cho
**1 custom + 1 add-on trên cùng HA**. Đổi email, khóa/thu hồi/reset không xóa lịch
sử trial. Trial không được gia hạn hoặc reset sang installation khác.

## Tài khoản admin

Admin đã tạo riêng cho email chủ tài khoản triển khai. Email/password ở file:
`/opt/apk-lab/input/rangdong/private/license-admin.txt` (quyền 0600, ngoài Git/ZIP).
Đăng nhập `/dashboard`, sau đó mở `/admin`. Không dán mật khẩu vào chat.
Khách không thể tự đăng ký email admin hoặc được cấp role chỉ bằng cách nhập email.

## Kiểm thử đã thực hiện

- 27 test backend: PostgreSQL/D1, đổi mật khẩu, thu hồi session, role, trial,
  thanh toán, race/rollback và số lượt gọi gateway khi tải dashboard/admin.
- 69 test HA/helper: có license gate, offline lease và hồi quy chức năng cũ.
- TypeScript, Next.js production build, Ruff và ZIP/checksum/secret scan.
- Live production: đăng ký/đăng nhập bằng email không nhận OTP, nhận trial lặp lại
  trả cùng key, kích hoạt custom/add-on và kiểm tra chữ ký bằng public key đã ghim.
- Live production: tài khoản khác bị chặn dùng thử trên cùng installation;
  khách không vào API admin, tài khoản admin đăng nhập được.
- Live PayOS: tạo QR gói tháng đúng 50.000đ, bỏ qua giá giả từ trình duyệt;
  đã hủy đơn thử và đối soát CANCELLED, không chuyển tiền và không cấp key trả phí.

Hai tài khoản `rd-test-...@example.invalid` / `rd-test2-...@example.invalid` và đơn
thử đã hủy được giữ trong lịch sử để audit, không làm tăng doanh thu.
**Chưa chuyển tiền thật, chưa thử nâng cấp trên HA/thiết bị đang chạy của anh.**

## ZIP bàn giao

Trong thư mục `dist/` của repository:

- `rangdong_smart-v0.3.0-licensed.zip`: custom, URL/key production đã gắn.
- `rangdong-key-helper-local-0.3.0-licensed.zip`: add-on build local từ source.
- `rangdong-source-0.3.0-licensed.zip`: toàn bộ source để tự push GitHub.
- `rangdong-license-server-1.0.0.zip`: bản sao source website/Worker.
- `SHA256SUMS.txt`: checksum các ZIP lần đóng hiện tại.

Bản `licensed` bật kiểm tra khi cấu hình mới/lấy key cloud mới, không ngắt điều
khiển thiết bị đã cấu hình. ZIP `setup` cũ không phải bản bật license; không dùng
nhầm. Không commit/push GitHub hoặc cài đè HA của anh trong lượt này.

## Cập nhật web: đổi mật khẩu và điện thoại

Khách/admin đổi mật khẩu trong `/dashboard` → **Đổi mật khẩu**, nhập mật khẩu cũ
và xác nhận mật khẩu mới. Các session cũ bị đăng xuất; license và đơn hàng giữ nguyên.
Dashboard/admin đã gom truy vấn D1, giảm polling; kiểm tra trình duyệt ở chiều
rộng 320/390/768/1280px, form đổi mật khẩu, tab ẩn, dữ liệu nháp và pagination.
Không sửa custom/add-on trong lần cập nhật web này.

Đã kiểm tra endpoint đổi mật khẩu trên tài khoản test production: mật khẩu cũ
và hai session cũ bị từ chối sau đổi, đăng nhập mới thành công, key/đơn giữ nguyên.
Không đổi mật khẩu admin hay tài khoản khách thật. Bốn lượt đo dashboard từ máy
phát triển: trước 2216/2043/2046/2048 ms; sau 1071/1075/1075/1089 ms. Đây là phép
đo nhỏ trên một đường mạng, không phải cam kết tốc độ mọi điện thoại/mạng.

## Giới hạn còn lại

Email không xác minh nên chưa có chức năng tự khôi phục mật khẩu qua email.
Người có toàn quyền HA vẫn có thể sửa source hoặc tạo lại toàn bộ danh tính;
không tuyên bố chống clone/reset vật lý tuyệt đối. Giữ secret production và
backup HA an toàn. Cần kiểm tra một khoản thanh toán thật trước khi mở bán rộng.
