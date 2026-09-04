# Rạng Đông Key Helper

Ứng dụng Home Assistant này (trước đây gọi là add-on) nhập các giá trị
`local_key` từ ứng dụng Rạng Đông Android chính thức trên điện thoại do bạn
kiểm soát. Ứng dụng không cần Tuya IoT Cloud project.

## Yêu cầu

- Home Assistant OS đã cài tích hợp tùy chỉnh **Rạng Đông Smart**.
- Điện thoại Android cùng mạng LAN với Home Assistant.
- Ứng dụng Rạng Đông chính thức đã cài với tên gói `com.rd.smart`.
- Điện thoại **đã root** và trình quản lý root có thể cấp quyền root cho ADB
  shell.
- Đã bật **Tùy chọn nhà phát triển → Wireless debugging** trên Android.

Chỉ bật Wireless ADB là chưa đủ nếu điện thoại chưa root. APK Rạng Đông không
bật chế độ gỡ lỗi và vô hiệu hóa Android backup, vì vậy helper không thể gắn vào
tiến trình riêng của ứng dụng nếu không có quyền root.

## Ghép đôi ADB lần đầu

1. Trên Android, mở **Tùy chọn nhà phát triển → Wireless debugging**.
2. Chọn **Pair device with pairing code**.
3. Nhập IP điện thoại, cổng ghép đôi tạm thời và mã sáu chữ số vào helper.
4. Bấm **Ghép đôi ADB** trước khi màn hình ghép đôi của Android hết hạn.
5. Quay lại màn hình Wireless debugging chính và chép **IP address & port** vào
   ô **Cổng kết nối ADB**.
6. Khi helper kiểm tra điện thoại lần đầu, chấp thuận yêu cầu cấp root từ
   Magisk hoặc trình quản lý root đang dùng.

Android thường cấp cổng ghép đôi và cổng kết nối khác nhau. Ghép đôi thành công
không có nghĩa cổng `5555` là cổng kết nối đúng.

## Nhập key bằng phiên ứng dụng đang đăng nhập

1. Đăng nhập vào ứng dụng Rạng Đông trên điện thoại và chờ danh sách nhà hoặc
   thiết bị tải xong.
2. Mở trang Ingress của helper và chọn **Dò bằng phiên app hiện có**.
3. Chờ helper hiển thị danh sách thiết bị; key đầy đủ chỉ được giữ tạm và giao
   diện chỉ hiển thị giá trị đã che.
4. Trong Home Assistant, mở **Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp →
   Rạng Đông Smart**.
5. Chọn **LAN nội bộ → Android bridge**, chọn Device ID đã nhập và hoàn tất
   cài đặt. Tích hợp sẽ kiểm tra key với thiết bị trong LAN.

## Đăng nhập từ helper

Nếu ứng dụng Android đang đăng xuất, nhập mã quốc gia, số điện thoại và mật khẩu,
sau đó bấm **Đăng nhập & dò**. Container Linux không giả lập giao thức cloud
riêng của ứng dụng. Thay vào đó, Frida gọi
`ThingHomeSdk.getUserInstance().loginWithPhonePassword(...)` bên trong tiến
trình ứng dụng gốc, rồi yêu cầu SDK trả về danh sách nhà và thiết bị của tài
khoản.

Mật khẩu không được ghi vào tùy chọn ứng dụng, tệp, log hoặc kho mã. Mật khẩu chỉ
tồn tại tạm thời trong bộ nhớ của trình duyệt, Python và tiến trình Android
trong lúc thực hiện yêu cầu. Nếu nhà cung cấp yêu cầu captcha, vé xác minh hoặc
một thử thách tương tác khác, hãy đăng nhập bằng ứng dụng chính thức rồi dùng
phương thức lấy phiên hiện có.

## Cơ chế bảo mật

- Giao diện web chỉ mở qua Ingress Home Assistant dành cho quản trị viên; helper
  kiểm tra `X-Remote-User-Id` với nhóm quản trị viên của Home Assistant và dùng
  CSRF token riêng cho mỗi tiến trình.
- Frida server được tải từ bản phát hành Frida chính thức trên GitHub, chọn đúng
  ABI Android và kiểm tra bằng SHA-256 đã ghim.
- Frida chỉ lắng nghe trên loopback của Android và được truy cập qua cổng chuyển tiếp
  ADB nội bộ của container. Helper dừng tiến trình Frida sau mỗi lần thao tác.
- Key đầy đủ chỉ được gửi đến bridge Home Assistant đã xác thực. Giao diện,
  phản hồi thành công và log chỉ chứa giá trị đã che.
- Bản ghi bridge đã nhập chỉ tồn tại trong bộ nhớ Home Assistant cho tới khi
  được dùng, bị xóa hoặc Home Assistant khởi động lại. Key được chấp nhận trong
  bước thiết lập local sẽ được lưu vào config entry của tích hợp vì cần thiết
  cho giao tiếp Tuya LAN đã mã hóa.

Sau khi nhập xong, hãy dừng hoặc gỡ helper nếu không còn cần. Nếu chưa hoàn
tất cài đặt, dùng **Xóa key tạm khỏi bridge** trước khi dừng ứng dụng.

Mã do dự án tự phát triển được cấp phép theo MIT. Image và agent đã biên dịch
cũng dùng các thành phần Frida theo giấy phép của dự án gốc; xem
[thông báo thành phần bên thứ ba](THIRD_PARTY_NOTICES.md) và
[giấy phép Frida](LICENSE.frida.txt) trong kho mã và image container.

## Xử lý sự cố

- **Ghép đôi ADB thất bại:** tạo mã ghép đôi mới và dùng cổng tạm thời hiển thị
  trong hộp thoại ghép đôi.
- **Kết nối ADB thất bại:** dùng cổng trên trang Wireless debugging chính; cổng
  này thường thay đổi sau khi khởi động lại hoặc tắt/bật Wireless debugging.
- **Yêu cầu root:** cấp quyền root cho `shell`/ADB trong trình quản lý root.
  Điện thoại chưa root không được hỗ trợ.
- **Ứng dụng chưa đăng nhập:** đăng nhập qua helper hoặc mở ứng dụng chính
  thức, hoàn tất captcha nếu có, rồi thử lại bằng phiên hiện tại.
- **Không có local key:** mở danh sách thiết bị trong ứng dụng chính thức trước.
  Thiết bị con phía sau hub có thể không có key LAN hoặc IP riêng để sử dụng.
- **Thiếu SDK sau khi ứng dụng cập nhật:** nhà sản xuất có thể đã thay đổi
  package hoặc lớp SDK ThingClips; hãy cập nhật helper trước khi thử lại.
