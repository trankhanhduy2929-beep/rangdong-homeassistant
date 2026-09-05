# Rạng Đông Key Helper

## Cloud: không cần Android hoặc Tuya IoT project

Yêu cầu Home Assistant OS có tích hợp Rạng Đông Smart **0.2.5 trở lên** (khuyên
dùng **0.2.6** để cập nhật hướng dẫn trên giao diện), add-on
**0.2.1**, máy amd64 hoặc aarch64 và kết nối Internet. Khởi động lại Home
Assistant sau khi cập nhật tích hợp. Không cần điền mục cấu hình Android.

1. Mở **Rạng Đông Key Helper → Mở giao diện web** bằng tài khoản HA quản trị.
2. Nhập email/mật khẩu Rạng Đông → **Đăng nhập cloud và lấy key**. Không cần APK.
3. Thêm tích hợp → LAN nội bộ → **Key Helper / bridge**, chọn thiết bị và IP.

Bộ tài nguyên đã tích hợp trong image từ 0.2.1. Lần đầu tự chuẩn bị thư viện;
chờ tối đa 240 giây. Không tải APK khi đăng nhập, không cần điện thoại Android.

### Nâng cao: import APK thủ công (không bắt buộc)

Nếu dùng image tự build không có bộ sẵn, chọn base `com.rd.smart.apk` và split `config.armeabi_v7a.apk`
   của Rạng Đông **5.7.2**, rồi bấm tải APK. Chỉ chấp nhận đúng hai SHA-256:

   | Tệp | SHA-256 |
   | --- | --- |
   | Base | `67c0fb602b55031117a09b4c0429be1270f60c8bf49e73dfec2b1aa6dbb43f8d` |
   | armeabi-v7a | `7b72cab2b62ab5835a4e96ec38076fc08ab8899cca6ec1c43679d3a3ad4e6060` |

   Dùng APK bạn sở hữu/được phép sử dụng. Bản 0.2.1 đã có sẵn cặp này.
   Có thể chép cặp APK đã dùng nghiên cứu vào ứng dụng **Tệp** trên iPhone và
   chọn từ trình duyệt; không cài APK lên iPhone. APK phiên bản khác bị từ chối.
Sau khi tải thủ công, nhập **email đăng ký Rạng Đông**, mật khẩu Rạng Đông và mã quốc gia `84`.
   Đây không phải mật khẩu Gmail/Google. Bấm **Đăng nhập** và chờ tối đa 240 giây.
Danh sách trả về chỉ hiển thị key đã che; key thật tự chuyển vào bridge HA.
Mở **Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp → Rạng Đông Smart →
   LAN nội bộ → Key Helper / bridge**, chọn thiết bị và IP. Tích hợp kiểm tra
   key với thiết bị LAN trước khi lưu. Cấu hình DP theo thiết bị.

**Giới hạn:** email đã lấy được key trên tài khoản thử; số điện thoại chưa được
kiểm chứng thành công. Hiện dùng endpoint vùng US của ứng dụng, chưa tự chuyển
vùng. Không vượt CAPTCHA/MFA; không tự thử lại mật khẩu, mỗi lần cách 60 giây.
Lấy được key không đồng nghĩa thiết bị Zigbee/BLE điều khiển được bằng Tuya LAN.
Chưa kiểm thử điều khiển trên thiết bị LAN thật trong môi trường phát triển.

iPhone có thể khác mạng nếu mở HA qua HTTPS đáng tin cậy. **Home Assistant phải
truy cập được mạng LAN thiết bị**; cloud không thay thế đường kết nối local.

Mật khẩu chỉ dùng tạm trong RAM/pipe đến worker; không lưu account/session vào
options hay log. APK tích hợp nằm ở `/opt/rangdong-apk`; APK nhập tay và cache
nằm trong `/data/cloud`, quyền 0700/0600. Nút xóa chỉ xóa bản nhập tay và cache,
không xóa tài nguyên gốc trong image. Backup add-on có thể chứa
APK/tài nguyên ứng dụng nên cũng cần bảo vệ. Key bridge chỉ tạm trong RAM; sau
khi cấu hình local, Home Assistant lưu key theo cơ chế cấu hình tích hợp.
Không gửi log chứa bí mật hoặc ảnh key lên issue. Chỉ dùng với tài khoản của bạn.

Nếu danh sách bridge mất do HA khởi động lại, đăng nhập lấy key lại. Nút
**Xóa key tạm khỏi bridge** nằm trong mục Android bổ sung, dùng được cho cả cloud.
Nếu còn yêu cầu import hai APK, kiểm tra add-on đã lên **0.2.1**, dừng/khởi
động lại add-on và tải lại trang; cập nhật HACS không tự cập nhật add-on.

## Android: phương án bổ sung

Các bước dưới đây chỉ dành cho cách lấy key từ SDK trong điện thoại Android.

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
