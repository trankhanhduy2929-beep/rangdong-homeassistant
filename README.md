# Rạng Đông Smart cho Home Assistant

Tích hợp tùy chỉnh cài qua HACS dành cho thiết bị **Rạng Đông Smart**, hỗ trợ
điều khiển trực tiếp bằng giao thức Tuya trong mạng LAN và vẫn giữ phương thức
xác thực QR cũ làm lựa chọn dự phòng.

> Nên dùng chế độ **LAN nội bộ** nếu ứng dụng Rạng Đông báo
> “please use the designated app to scan the code to log in” (hãy dùng ứng
> dụng được chỉ định để quét mã đăng nhập).

[Mở kho này trong HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=trankhanhduy2929-beep&repository=rangdong-homeassistant&category=integration)

[Thêm kho này vào kho ứng dụng Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Ftrankhanhduy2929-beep%2Frangdong-homeassistant)

## Tính năng

- Dò thiết bị Wi-Fi Rạng Đông tương thích Tuya bằng gói tin UDP trong LAN.
- Tự động nhận diện địa chỉ IP, Device ID, Product ID và phiên bản giao thức
  khi thiết bị có phát các thông tin này.
- Điều khiển trực tiếp qua TCP cổng `6668`; chế độ LAN nội bộ không dùng cloud
  hoặc MQTT.
- Tự động thử giao thức Tuya từ `3.5` đến `3.1`.
- Lấy `local_key` một lần từ Tuya IoT Cloud project do chính người dùng quản
  lý. Access ID và Access Secret không được lưu lại.
- Nhập dữ liệu một lần từ TinyTuya, Tuya API và các định dạng JSON xuất bởi LocalTuya
  phổ biến.
- Android bridge có xác thực để nhận dữ liệu từ helper cục bộ và tự động liệt
  kê Device ID trong luồng cài đặt.
- Add-on **Rạng Đông Key Helper** có Ingress dành cho quản trị viên, đăng nhập
  cloud lấy key không cần Android; giữ Wireless ADB/Frida làm phương án bổ sung.
- Tái sử dụng `local_key` đã có trong một cấu hình Rạng Đông QR/cloud đang hoạt
  động.
- Tạo công tắc cho từng DP kiểu boolean và cảm biến chẩn đoán trạng thái LAN có
  ảnh chụp dữ liệu DP hiện tại.
- Dịch vụ `rangdong_smart.send_command` cho DP dạng số ở chế độ local và DP
  cloud cũ.
- Các cấu hình QR đã tạo trước đây vẫn tiếp tục hoạt động và có thể được chọn
  rõ ràng khi cài đặt.

## Giới hạn quan trọng

**Đăng nhập cloud không cần Android:** add-on **0.2.0** kết hợp tích hợp
**0.2.5** có giao diện tải APK, đăng nhập Rạng Đông và chuyển local key vào
Home Assistant. Nghiên cứu đã lấy được key của 9 thiết bị bằng email.
Không cần điện thoại root hoặc Tuya IoT project. Chưa kiểm thử điều khiển LAN
trên các thiết bị thật đó. Xem [hướng dẫn cloud](rangdong_key_helper/DOCS.md).

Quét mạng LAN **không thể lấy được** `local_key` của thiết bị. Đây là thông tin
xác thực riêng cho từng thiết bị và là thành phần bắt buộc của giao thức Tuya
LAN đã mã hóa. Luồng cài đặt sẽ dò IP/Device ID trước, sau đó cho phép lấy key
một lần từ nguồn đã được cấp quyền, nhập từ JSON hoặc nhập thủ công. Key luôn
được kiểm tra trực tiếp với thiết bị trong LAN trước khi tạo cấu hình.

Không dùng mật khẩu tài khoản Rạng Đông thay cho local key. Tuyệt đối không đưa
local key, mật khẩu tài khoản, token hoặc bí mật lấy từ APK vào issue, log công
khai hay kho GitHub.

## Cài đặt qua HACS

1. Cài đặt và mở HACS trong Home Assistant.
2. Mở **HACS → Tích hợp (Integrations) → ⋮ → Kho tùy chỉnh (Custom
   repositories)**.
3. Thêm `trankhanhduy2929-beep/rangdong-homeassistant`, sau đó chọn loại
   **Integration**.
4. Tải **Rạng Đông Smart** và khởi động lại Home Assistant.
5. Mở **Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp**, rồi chọn
   **Rạng Đông Smart**.

HACS chỉ cài **tích hợp Rạng Đông Smart**. Add-on **Rạng Đông Key Helper**
phải cài riêng từ kho ứng dụng Home Assistant theo phần dưới đây.

## Cài Rạng Đông Key Helper

Kho GitHub này đồng thời là một kho ứng dụng Home Assistant:

1. Bấm liên kết **Thêm kho này vào kho ứng dụng Home Assistant** ở đầu trang,
   hoặc mở **Cài đặt → Ứng dụng (Apps) → Kho ứng dụng (App store) → Kho lưu trữ
   (Repositories)** rồi thêm:

   ```text
   https://github.com/trankhanhduy2929-beep/rangdong-homeassistant
   ```

2. Cài **Rạng Đông Key Helper** và khởi động ứng dụng thủ công.
3. Cập nhật tích hợp lên **0.2.5**, khởi động lại Home Assistant trước khi lấy key.
4. Mở giao diện web helper → mục **Cloud**. Tải lên hai APK Rạng Đông 5.7.2
   được hỗ trợ theo [hướng dẫn](rangdong_key_helper/DOCS.md).
5. Nhập email và mật khẩu tài khoản **Rạng Đông**, rồi bấm đăng nhập lấy key.
   Không nhập mật khẩu Google; không cần quét QR hay Android.
6. Quay lại **Thêm tích hợp → Rạng Đông Smart → LAN nội bộ → Key Helper / bridge**
   và chọn Device ID đã import.

Mục **Android** là phương án bổ sung, chỉ mục này mới cần root và ADB.
Cloud chạy thư viện native từ APK do bạn cung cấp trong worker Linux riêng.
APK được kiểm tra SHA-256 trước khi dùng; không đóng gói APK hay bí mật ứng dụng
vào image/GitHub. Tài khoản, mật khẩu và phiên cloud không được lưu vào options
hay log. iPhone có thể mở Ingress từ xa qua HTTPS; Home Assistant vẫn phải
truy cập được mạng LAN của thiết bị để điều khiển local.

Nếu tài khoản yêu cầu captcha, mã xác minh hoặc gặp giới hạn “designated app”,
hãy đăng nhập trực tiếp bằng ứng dụng Rạng Đông chính thức rồi dùng chức năng
dò bằng phiên ứng dụng hiện có. Xem
[hướng dẫn chi tiết của Key Helper](rangdong_key_helper/DOCS.md).

## Thiết lập LAN nội bộ

1. Chọn **LAN nội bộ (khuyên dùng)**.
2. Bật thiết bị Wi-Fi Rạng Đông và bảo đảm thiết bị cùng mạng LAN với Home
   Assistant.
3. Chọn thiết bị tìm được. Nếu danh sách trống, chọn **Nhập thủ công**, sau đó
   nhập địa chỉ IP và Device ID.
4. Chọn nguồn local key:
   - **Android bridge** sau khi helper đã gửi dữ liệu thiết bị từ ứng dụng
     Rạng Đông;
   - **Lấy một lần từ Tuya Cloud** nếu thiết bị đã liên kết với Tuya IoT Cloud
     project của bạn;
   - **Nhập dữ liệu JSON đã xuất** từ TinyTuya, LocalTuya hoặc Tuya API;
   - **Cloud entry đã xác thực** nếu cấu hình QR đang hoạt động đã có cùng thiết
     bị; hoặc
   - **Nhập local key thủ công**.
5. Giữ **Tự động (Auto)** cho phiên bản giao thức, trừ khi đã biết chính xác
   thiết bị cần phiên bản nào. Tích hợp sẽ đọc thử thiết bị trước khi lưu.

Mỗi thiết bị được tạo thành một mục cấu hình (config entry) riêng. Hãy chạy
**Thêm tích hợp** lại cho từng thiết bị Wi-Fi khác.

### Lấy local key ở đâu

Ứng dụng chính thức thường không hiển thị local key. Các nguồn được hỗ trợ gồm:

- đăng nhập Rạng Đông bằng email trong **Key Helper 0.2.0**, dùng cặp APK được
  hỗ trợ, không cần Android hoặc Tuya IoT project;
- bản dữ liệu thiết bị Tuya/Rạng Đông đã xuất từ nguồn được cấp quyền hoặc một tích hợp local
  hiện có đã chứa key;
- thông tin thiết bị trong Tuya developer/cloud project do bạn quản lý; hoặc
- trích xuất riêng tư, có sự đồng ý từ điện thoại Android của chính bạn đang
  đăng nhập tài khoản.

### Lấy key một lần từ Tuya Cloud

Tích hợp có thể lấy local key từ Tuya IoT Cloud project do bạn quản lý:

1. Tạo hoặc mở một cloud project trên Tuya IoT Platform.
2. Liên kết tài khoản ứng dụng Tuya/Rạng Đông hoặc đúng thiết bị cần dùng với
   project, sau đó bật các quyền API quản lý thiết bị cần thiết.
3. Trong luồng cài đặt, chọn **Lấy một lần từ Tuya Cloud**.
4. Nhập **Access ID**, **Access Secret**, trung tâm dữ liệu và Device ID.
5. Xác nhận địa chỉ LAN. Tích hợp kiểm tra key trực tiếp với thiết bị và chỉ lưu
   cấu hình local đã hoạt động.

Access ID, Access Secret và phản hồi từ cloud không được lưu trong config entry
hoặc dữ liệu chẩn đoán của Home Assistant. Có thể tắt cloud project sau khi
nhập thành công nếu không còn dùng ở nơi khác.

Rạng Đông là ứng dụng OEM nên một số tài khoản không thể liên kết với Tuya IoT
project thông thường. Tích hợp không thể vượt qua giới hạn phía máy chủ này.
Nếu không liên kết được, dùng chế độ cloud của Key Helper, dữ liệu JSON đáng
tin cậy hoặc trích xuất riêng tư từ điện thoại Android của chính bạn.

### Nhập dữ liệu JSON

Chọn **Nhập dữ liệu JSON đã xuất** và dán dữ liệu đáng tin cậy có Device ID cùng một
trong các trường key: `key`, `local_key`, `localKey` hoặc `localkey`. Các định
dạng được hỗ trợ gồm:

- mảng `devices.json` của TinyTuya;
- đối tượng thiết bị từ Tuya Cloud/mobile API;
- các bản xuất dữ liệu LocalTuya phổ biến; và
- đối tượng hoặc từ điển dùng Device ID làm khóa.

JSON chỉ được xử lý một lần trong bộ nhớ, không được lưu hoặc hiển thị lại. Nếu
bản dữ liệu có nhiều thiết bị, luồng cài đặt sẽ hiển thị danh sách không chứa key
để người dùng chọn.

Phân tích APK cho thấy SDK Android sau khi đăng nhập lưu key trong bộ nhớ đệm
thiết bị riêng và cung cấp cho ứng dụng qua `DeviceBean.localKey`. Việc đọc bộ
nhớ đệm riêng này thường cần điện thoại test đã root/bật gỡ lỗi hoặc công cụ
kiểm tra lúc chạy như Frida. Chỉ thực hiện trên tài khoản và điện thoại của
chính bạn, giữ key ở chế độ riêng tư và tuyệt đối không đưa key vào kho này.

### Key Helper / bridge: nhập key local một lần

Nên dùng ứng dụng Home Assistant chỉ dành cho quản trị viên đã mô tả ở trên.
Ứng dụng lấy key qua cloud hoặc SDK Android, kiểm tra key dài 16 byte và gửi key
qua Supervisor đến địa chỉ API có xác thực của tích hợp. Giao diện chỉ hiển thị
giá trị đã che.

Người dùng nâng cao vẫn có thể tự gửi một bản dữ liệu đáng tin cậy:

```sh
curl -X POST \
  -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @rangdong-devices.json \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import
```

Dữ liệu gửi (payload) có thể dùng `devId`/`deviceId` cùng với `localKey`, `local_key` hoặc
`key`; các trường tùy chọn gồm `name`, `ip`, `productId` và `version`. Sau khi
POST, chọn **Android bridge** trong luồng cài đặt rồi bấm **Làm mới danh sách
key**. Luồng cài đặt chỉ liệt kê Device ID, không hiển thị key thô; sau đó kiểm
tra từng thiết bị đã chọn qua LAN và chỉ lưu cấu hình local hoạt động. Bridge
chỉ giữ key đã nhập trong bộ nhớ và xóa key sau khi dùng xong.

Để chỉ xem thông tin đã che hoặc xóa toàn bộ danh sách tạm:

```sh
curl -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import

curl -X DELETE \
  -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import
```

Chỉ gửi dữ liệu qua HTTPS hoặc một mạng LAN đáng tin cậy. Không đưa mật khẩu
Rạng Đông, token Home Assistant hay local key thô vào issue hoặc kho công khai.
Chế độ cloud cần đúng cặp APK được hỗ trợ, không cần Android root. Email đã
được kiểm chứng; không bảo đảm tài khoản điện thoại hay mọi vùng cloud đều
hoạt động. Không bỏ qua CAPTCHA hoặc xác minh tài khoản.

Bộ quét LAN không thể suy ra key từ gói tin quảng bá. Khi không có local key
khớp, tích hợp có thể nhận diện thiết bị nhưng không thể giải mã trạng thái hoặc
gửi lệnh local.

## Yêu cầu mạng

- Home Assistant và thiết bị phải cùng mạng IPv4 LAN/VLAN.
- Cho phép các cổng dò UDP `6666`, `6667` và `7000`.
- Cho phép cổng điều khiển TCP `6668`.
- Bản cài Docker có thể cần chế độ mạng host để nhận được gói tin broadcast từ
  mạng vật lý. Với Home Assistant Container, dùng `network_mode: host` hoặc
  thiết kế mạng tương đương có chuyển tiếp các cổng này.
- Guest Wi-Fi isolation, client isolation và VLAN định tuyến thường chặn việc
  dò hoặc điều khiển thiết bị.

## Phân biệt thiết bị Wi-Fi và Zigbee

Luồng local này điều khiển thiết bị **Wi-Fi** tương thích Tuya. Đèn hoặc cảm
biến Zigbee thường chỉ xuất hiện phía sau gateway và không có local key Wi-Fi
có thể sử dụng trực tiếp. Với thiết bị Zigbee, hãy ghép đôi bằng ZHA hoặc
Zigbee2MQTT, hoặc cấu hình gateway qua một tích hợp cloud/local phù hợp.

## Gửi lệnh DP thô

Thiết bị local dùng DP ID dạng số. Cảm biến trạng thái LAN hiển thị bản đồ DP
hiện tại trong thuộc tính. Ví dụ bật DP nguồn:

```yaml
action: rangdong_smart.send_command
data:
  device_id: "device-id-tu-cam-bien-trang-thai-LAN"
  dp_id: 1
  value: true
```

Cấu hình QR/cloud cũ vẫn chấp nhận mã DP có tên:

```yaml
action: rangdong_smart.send_command
data:
  device_id: "device-id-tu-cam-bien-trang-thai-cloud"
  code: switch_led
  value: true
```

Chỉ gửi kiểu giá trị mà thiết bị hỗ trợ. Thiết bị có thể từ chối nếu kiểu dữ
liệu DP không hợp lệ.

## Dùng QR làm phương án dự phòng

Chọn **QR cloud cũ** để tiếp tục dùng luồng User Code và QR trước đây. Nếu ứng
dụng Rạng Đông liên tục báo lỗi chỉ dành cho ứng dụng được chỉ định, ví dụ
`E0020003`, đây là giới hạn xác thực phía máy chủ; thay prefix của mã QR không
thể vượt qua giới hạn này. Hãy dùng LAN nội bộ khi đã có local key.

## Cài đặt thủ công

Sao chép thư mục `custom_components/rangdong_smart` vào:

```text
<config>/custom_components/rangdong_smart
```

Khởi động lại Home Assistant, sau đó thêm **Rạng Đông Smart** trong
**Cài đặt → Thiết bị & dịch vụ**.

## Xử lý sự cố

- **Không tìm thấy thiết bị:** kiểm tra chế độ mạng host, subnet, quy tắc
  broadcast và trạng thái nguồn của thiết bị; thử nhập IP/Device ID thủ công.
- **Không thể kết nối:** kiểm tra TCP `6668`, tường lửa và chế độ cô lập thiết
  bị Wi-Fi.
- **Local key không hợp lệ:** xác nhận key thuộc đúng thiết bị; giữ giao thức ở
  chế độ **Tự động** rồi thử lại.
- **Lỗi lấy key từ Tuya Cloud:** kiểm tra trung tâm dữ liệu, quyền API, tài
  khoản/thiết bị đã liên kết và Access ID/Access Secret. Tài khoản OEM Rạng
  Đông có thể không hỗ trợ liên kết Tuya IoT.
- **Không tìm thấy key trong JSON:** bảo đảm dữ liệu có đúng Device ID và
  local key dài 16 byte; không dán mật khẩu tài khoản Rạng Đông.
- **Thiết bị là Zigbee:** dùng ZHA, Zigbee2MQTT hoặc tích hợp gateway; quét
  Wi-Fi không thể ghép trực tiếp thiết bị Zigbee con.
- **Địa chỉ IP thay đổi:** mở mục cấu hình của tích hợp, chọn **Cấu hình lại
  (Reconfigure)** rồi nhập địa chỉ và local key mới. Nên đặt DHCP reservation
  để thiết bị luôn có IP ổn định.
- **Helper không đăng nhập được hoặc gặp captcha:** đăng nhập bằng ứng dụng
  Rạng Đông chính thức trên điện thoại đã root, mở danh sách thiết bị, sau đó
  chọn **Dò bằng phiên app hiện có** trong helper.

## Phát triển và kiểm tra

Mã tích hợp cài đặt nằm trong `custom_components/rangdong_smart`. Mã ứng dụng
Home Assistant nằm trong `rangdong_key_helper`. Các lệnh kiểm tra của dự án:

```sh
ruff check custom_components/rangdong_smart tests \
  rangdong_key_helper/rootfs/app/rangdong_helper rangdong_key_helper/tests
PYTHONPATH=custom_components:rangdong_key_helper/rootfs/app pytest -q
cd rangdong_key_helper/agent && npm ci && npm run build
```

Kho mã nguồn chủ ý không chứa tài khoản thật, mật khẩu, local key, cloud token
hoặc bí mật ứng dụng lấy từ APK.

## Giấy phép

Phần mã do dự án tự phát triển được phát hành theo giấy phép MIT. Image của
key helper và agent đã biên dịch có chứa các thành phần Frida theo giấy phép từ
dự án gốc; xem [thông báo thành phần bên thứ ba](rangdong_key_helper/THIRD_PARTY_NOTICES.md)
và [giấy phép Frida](rangdong_key_helper/LICENSE.frida.txt). Rạng Đông,
ThingClips, Tuya và các tên sản phẩm liên quan là nhãn hiệu của chủ sở hữu
tương ứng.
