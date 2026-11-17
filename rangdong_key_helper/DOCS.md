# Rạng Đông Key Helper 0.3.4

Giao diện mới chỉ có **License**, **tài khoản Rạng Đông** và **thiết bị đã lấy key**.
Không cần Android root, ADB/Frida hoặc import APK. Bộ đăng nhập đã tích hợp sẵn.

## Sử dụng

1. Cập nhật custom Rạng Đông Smart **0.3.4** và khởi động lại Home Assistant.
2. Mở add-on bằng tài khoản HA quản trị. Nếu yêu cầu license, bấm **Nhận dùng
   thử / mua / xem key**, đăng ký email + mật khẩu (không cần OTP), nhận trial
   hoặc thanh toán PayOS và sao chép key.
3. Nhập License Key vào add-on → **Kích hoạt**. Cùng key dùng cho một add-on và
   một custom integration trên cùng HA; các thiết bị trong HA dùng chung.
4. Nhập email/mật khẩu **Rạng Đông** → **Đăng nhập và lấy key**. Đây không phải
   mật khẩu email. Chờ tối đa 240 giây, mỗi lần đăng nhập cách nhau ít nhất 60 giây.
5. Thêm tích hợp → Rạng Đông Smart → LAN nội bộ → chọn thiết bị đã dò hoặc nhập
   Device ID, IP và local key hiển thị trong add-on.

Mục **Cấu hình** của custom cũng có form License Key. Danh tính và license dùng
chung qua HA nên không cần nhập cùng key ở từng thiết bị. Add-on có suất riêng,
custom có suất riêng. Khi chuyển/cài lại HA tạo danh tính mới, liên hệ admin reset.

Trial miễn phí 24 giờ từ lần kích hoạt đầu tiên; một lần/tài khoản và installation.
Gói tháng 50.000đ/30 ngày từ khi thanh toán; vĩnh viễn 200.000đ. Trial đã dùng không
được reset sang HA khác hoặc gia hạn thêm. Email website không cần giống email Rạng Đông.

Device ID và local key được hiển thị đầy đủ cho quản trị viên qua Ingress, có nút
**Sao chép**. Không gửi ảnh chụp hoặc chia sẻ key. Nút **Xóa key tạm khỏi bridge**
không xóa cấu hình thiết bị đã lưu trong HA. Không còn nút/API upload hoặc xóa APK
ở giao diện này.

## License và điều khiển thiết bị

Bản `licensed` kiểm tra license khi thêm cấu hình, polling và gửi lệnh điều khiển.
License hết hạn hoặc bị thu hồi sẽ khóa điều khiển và làm entity không khả dụng,
nhưng không xóa config entry hay local key đã lưu. Gia hạn hoặc kích hoạt key mới
rồi tải lại tích hợp để tiếp tục.

Custom integration dùng lease đã ký khi server tạm mất mạng; lease tối đa 72 giờ
và bị vô hiệu khi server trả trạng thái khóa/thu hồi. Add-on yêu cầu trạng thái
`active` khi xác minh, nên khi server không truy cập được, chức năng lấy/xem key
tạm khóa cho đến lần xác minh sau. Đây không phải mất license và không cần mua lại.

Bản `setup` báo **chế độ tương thích** vì chủ dự án chưa cấu hình server/public
key. Bản này vẫn hoạt động như trước; chỉ bản `licensed` đã cấu hình mới ép license.
Chủ dự án xem [hướng dẫn triển khai](../LICENSE_DEPLOY_VI.md).

Home Assistant vẫn phải truy cập được LAN thiết bị. iPhone có thể mở HA từ xa
qua HTTPS. Không vượt CAPTCHA/MFA, không bảo đảm mọi tài khoản/vùng cloud hay
thiết bị Zigbee/BLE có thể điều khiển bằng Tuya LAN.

## Nâng cấp an toàn

Sao lưu HA trước. Không xóa dữ liệu add-on hoặc `.storage` để nâng cấp. Các options
Android cũ nếu còn trong backup được bỏ qua; không cần nhập. Trước khi chủ dự án
push/build image mới, dùng ZIP add-on local (đã bỏ trường `image`) để Supervisor
build từ source. Không cài song song hai add-on dùng cùng suất license.
