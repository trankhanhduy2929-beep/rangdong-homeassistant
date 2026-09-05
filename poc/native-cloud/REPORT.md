# Báo cáo nghiên cứu cloud native Rạng Đông — 04/09/2026

## Kết quả cập nhật ngày 05/09/2026: email đã lấy được key

- Đọc tài khoản mới từ file riêng: email + mật khẩu Rạng Đông. Không ghi giá trị vào log.
- Chọn API `thing.m.user.email.password.login` 3.0 theo `LoginBusiness.s` trong APK;
  không dùng mobile API cho email. Tên trường `Gmail` viết hoa được nhận diện.
- Token, đăng nhập, home list và các API thiết bị đều HTTP 200, `success=true`.
  Chữ ký phản hồi và AES-GCM được xác minh; có `sid` và `ecode`.
- Sau sửa xử lý `deviceList` thiếu/null ở kết quả local bổ sung, lấy được
  **9 cặp Device ID/local key hợp lệ**; đã xuất JSON quyền 0600 ra ngoài repo.
- Bộ `validate_records` của helper nhận đủ 9 bản ghi. Đây là kiểm tra cấu trúc,
  **không phải** kiểm thử điều khiển thiết bị LAN.
- Không cần Android root hoặc Tuya IoT project cho lần thử email này.
- Add-on hiện tại chưa có worker/giao diện cloud; không đổi version hoặc tự push.

Lần email đầu đăng nhập và đọc API thành công nhưng parser dừng ở danh sách local
bổ sung. `ThingListDataBean.addDevices` trong APK bỏ qua danh sách null/rỗng; PoC
đã sửa tương ứng và thêm regression test, vẫn từ chối sai kiểu và key xung đột.
Lần chạy tiếp hoàn tất xuất key. Không lưu phiên đăng nhập hoặc dump cloud response.

Các phần dưới lưu lại **lịch sử nghiên cứu trước khi nhận tài khoản email mới**.
Những nhận định “chưa đăng nhập/lấy key” bên dưới không còn là trạng thái hiện tại.

## Phát hiện đã xác minh

Thử nghiệm thực tế trên Linux amd64 với APK `com.rd.smart` 5.7.2 do người dùng
cung cấp, Unidbg 0.9.8, Java 21. Không sửa APK gốc.

| Bước | Kết quả |
| --- | --- |
| Khởi tạo native từ APK, chứng thư và tài nguyên | Chạy được |
| `getChKey` | Chuỗi 8 ký tự, không ghi giá trị |
| `getEncryptoKey(requestId, null)` | Khóa 16 byte, không ghi giá trị |
| `encryptPostData` / `computeDigest` | 16 byte / 32 ký tự |
| Ký bằng native command 1 | 64 ký tự, ổn định khi đầu vào giống nhau |
| Token API 2.0, số giả | HTTP 200, `success=true` |
| Chữ ký phản hồi, AES-GCM và JSON | Xác minh/giải mã được trong request token kiểm tra lại |
| Token API với tài khoản được cung cấp | HTTP 200, `success=true` |
| Mobile password login 3.0, một lần | HTTP 200, `success=false`, `USER_PASSWD_WRONG` |

Không thử lại mật khẩu, không thử biến thể số điện thoại hoặc API hàng loạt.
Mã `USER_PASSWD_WRONG` là kết quả server, chưa đủ để phân biệt mật khẩu đã đổi,
thông tin tài khoản không khớp hay chi tiết client đăng nhập còn thiếu. Không kết
luận rằng chỉ đổi mật khẩu là chắc chắn hoạt động.

Trong quá trình thử, DNS từng lỗi ở cả cloud và GitHub rồi phục hồi. Sau phục hồi
đã kiểm tra lại token cùng xác minh chữ ký phản hồi. **Trở ngại hiện tại là chưa có
phiên đăng nhập thành công**, không còn lấy sự cố DNS làm kết luận cuối cùng.

## Giao thức đã đối chiếu

- Endpoint thử nghiệm: `https://a1-us.iotbing.com/api.json`.
- POST form chứa metadata, ciphertext `postData` và `sign`; URL không chứa phiên.
- `et=3`: AES-GCM, nonce 12 byte đứng **đầu** ciphertext và tag 16 byte, Base64.
- Request chưa đăng nhập: khóa native lấy từ request ID, ecode null.
- Chuỗi ký chỉ lấy whitelist, sort tên trường, bỏ giá trị rỗng. `postData` thay
  bằng MD5 hex đã đổi thứ tự các đoạn 8 ký tự; ciphertext gốc vẫn nằm trong form.
- Khởi tạo command 0 nhận app secret rồi app ID; command 1 ký chuỗi canonical.
- Chữ ký phản hồi là MD5 của `result=<ciphertext>||t=<timestamp>||<request-key>`.
  Kiểm tra trước khi giải mã; GCM tiếp tục kiểm tra authentication tag.
- Payload đăng nhập dùng MD5 mật khẩu rồi RSA PKCS#1 v1.5 theo public key/exponent
  từ token API. Chưa xác minh thành công cuối luồng với tài khoản hợp lệ.

## Bằng chứng từ APK trong workspace nghiên cứu

Các đường dẫn sau tương đối với `/opt/apk-lab/input/rangdong`, không đóng gói vào Git:

- `analysis/apktool_base/AndroidManifest.xml`: package và thông tin Android.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/common/utils/AesGcmUtil.smali`:
  `encryptBytes2BytesAppendNonce`, `decryptBytesAppendedNonce2Bytes`.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/network/ThingApiParams.smali`:
  `getEncryptPostDataString`, `getRequestBody`, `getRequestUrl`, `initUrlParams`.
- `analysis/apktool_base/smali_classes4/com/thingclips/sdk/network/ThingApiSignManager.smali`:
  whitelist, `generateSignatureSdk`, `postDataMD5Hex`, `swapSignString`.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/network/Business.smali`:
  `verifyResponseResult`, giải mã và giải nén phản hồi.
- `analysis/apktool_base/smali_classes5/com/thingclips/sdk/user/pqdbppq.smali`:
  `thing.m.user.mobile.passwd.login`, phiên bản 3.0, `options`, `ifencrypt`.
- `analysis/apktool_base/smali_classes14/com/thingclips/smart/security/jni/SecureNativeApi.smali`:
  chữ ký phương thức JNI.

PoC có shim kiểu đối tượng X509Certificate và callback `checkStatus` để nạp JNI.
Đây không phải môi trường Android hoàn chỉnh hoặc bằng chứng vượt attestation;
không dùng shim để bỏ qua yêu cầu xác minh mà server trả về.

## Giả thuyết và phần còn thiếu

- Có thể tái sử dụng native client trong worker add-on, nhưng mới xác minh bước
  trước đăng nhập và phản hồi từ chối mật khẩu.
- Chưa xác nhận `sid`, `ecode`, domain sau đăng nhập, home list, device list, local
  key, refresh session hoặc khả năng điều khiển thiết bị thật.
- Chưa có worker JSON-lines, giao diện tải APK hoặc tích hợp cloud vào bridge.
- Chưa kiểm thử aarch64; không tăng phiên bản add-on/integration hay phát hành HACS.
- Không có tài khoản, mật khẩu, token, chữ ký request hoặc local key trong báo cáo.

## Kế hoạch kiểm thử tiếp

1. Chủ tài khoản kiểm tra thông tin đăng nhập trên app chính thức; không gửi lại
   mật khẩu trong chat. Chạy PoC qua terminal nhập ẩn bằng thông tin hợp lệ.
2. Khi đăng nhập thành công, xác minh vùng cloud, cấu trúc phiên và danh sách nhà.
3. Chỉ đọc thiết bị thuộc phiên đã xác thực; đếm số key hợp lệ, không log giá trị.
4. Thêm fixture giả cho phản hồi thực tế, rồi mới nối vào bridge/import hiện có.
5. Kiểm thử container và kiến trúc trước khi xuất bản add-on.

## Kiểm thử mã nguồn đã lưu

### Đối chiếu lại luồng đăng nhập ngày 05/09/2026

Chủ tài khoản xác nhận vẫn đăng nhập được trên app chính thức. Truy vết
`analysis/apktool_base/smali_classes8/com/thingclips/smart/login/skt/data/LoginRepository$loginWithPassword$1.smali`
cho thấy nhánh số điện thoại gọi `LoginBusiness.r`, không phải hàm UserBusiness
3.0 đã chọn ở PoC ban đầu.
`analysis/apktool_base/smali_classes8/com/thingclips/smart/login/skt/business/LoginBusiness.smali`
dựng API `thing.m.user.mobile.passwd.login` phiên bản **4.0**, options gồm `group`
và `mfaCode`. Đã sửa PoC theo nhánh này; mã MFA để rỗng khi chưa có yêu cầu xác minh.
Nếu server yêu cầu MFA, PoC vẫn dừng, không bỏ qua xác minh.

Kết quả `USER_PASSWD_WRONG` phía trên là thử nghiệm **bản 3.0 trước sửa**, không
phải kết quả bản 4.0. Sau đó đã thử bản 4.0 bằng định dạng số ban đầu và một lần
bỏ số 0 đầu theo helper hiện có: cả hai vẫn trả `USER_PASSWD_WRONG`. Token thành
công, phản hồi có chữ ký hợp lệ và giải mã được. Đã dừng, không thử thêm biến thể.
Chênh lệch API là phát hiện từ mã APK, chưa chứng minh đó là nguyên nhân duy nhất
của lỗi hay bản sửa đã đăng nhập được. Không suy ra mật khẩu người dùng sai.

### Đường đi local key tìm thấy trong APK

1. `smali_classes4/com/thingclips/sdk/home/o0Oo0oo.smali`, `queryHomeList`, gọi
   `o00O0O.OooO00o` để lấy danh sách nhà.
2. `smali_classes4/com/thingclips/sdk/home/o00O0O.smali` gọi
   **`m.life.group.location.list` 7.0**, parse danh sách `HomeResponseBean` có
   `gid`/`id`. PoC cũ dùng API home list từ tài liệu tham khảo, nay đã sửa theo APK.
3. `smali_classes4/com/thingclips/sdk/home/o00oO0o.smali`, `OooO0Oo(J)`, tạo
   **`m.life.my.group.device.list` 2.2** với payload `gid`, yêu cầu phiên đăng nhập.
   Luồng xử lý phản hồi parse danh sách `DeviceRespBean`.
4. Cùng lớp, `OooO0O0(J, callback)`, gọi **`m.life.app.smart.local.device.list`
   1.1** với `homeId` và `groupType=homeGroup`. Kết quả là
   `ThingLocalDeviceListDataBean.deviceList`, gồm `DeviceRespBeanEx` kế thừa
   `DeviceRespBean`.
5. `smali_classes10/com/thingclips/smart/interior/device/bean/DeviceRespBean.smali`
   có trường **`localKey`**; `getLocalKey()` trả trực tiếp trường này, không sinh
   một key chung từ APK. `devKey` là trường riêng.
6. `smali_classes14/com/thingclips/smart/sdk/bean/DeviceBean.smali`, `getLocalKey()`,
   đọc từ DeviceRespBean khi dùng cache mới, nếu không thì đọc trường localKey
   trong bean. Đây là getter helper Android/Frida đang sử dụng.

Các đường dẫn bắt đầu với `smali_classes` ở phần này tương đối với
`analysis/apktool_base`. Đây là bằng chứng tĩnh về cấu trúc app, **không phải**
bằng chứng server hiện trả key cho tài khoản thử nghiệm. Root cho phép helper
đọc dữ liệu của app đã đăng nhập; root không tạo local key và không thay thế
xác thực cloud. Chưa xác minh API chia sẻ thiết bị hay trường hợp gateway/thiết bị con.

### Mã bổ sung và kiểm thử ngày 05/09/2026

- `CloudDevices.java`: luồng chỉ đọc ba API đã truy vết, chỉ dùng ID nhà trả về từ
  phiên hiện tại; không nhận ID tùy ý. Giới hạn 100 nhà/5000 thiết bị và dừng khi lỗi.
- Chỉ nhận `devId` + `localKey` 16 byte, không suy đoán key từ `devKey`/`secKey`,
  không nhận metadata tùy ý. Không in key; key xung đột làm dừng toàn bộ snapshot.
- `--device-probe`: sau đăng nhập, chạy luồng trên và chỉ in số thiết bị có key hợp lệ.
- Request không có business payload không gửi `postData`, khớp APK.
- Sửa `prepare.py` sau kiểm thử APK thật: trước đây nhầm một chuỗi 20 ký tự không
  liên quan là app ID thứ hai. Nay nhận duy nhất cặp hằng 20/32 ký tự liền nhau,
  vẫn dừng khi không rõ; không ghi giá trị hằng vào repo. Đây vẫn là bộ trích xuất
  cho phiên bản APK đã nghiên cứu, không phải bộ phân tích APK tổng quát.
- 13 kiểm tra CloudDevices với dữ liệu giả đạt; 10 kiểm tra giao thức đạt;
  6 kiểm tra chuẩn bị APK đạt. Chưa có kiểm thử lấy key trên cloud thật.

### Trở ngại tích hợp add-on ở giai đoạn thử số điện thoại

Chưa có phiên cloud hợp lệ để xác minh danh sách nhà, domain sau đăng nhập và
key thực tế. Không đưa nút “lấy key không cần Android” vào add-on rồi tuyên bố
hoạt động chỉ dựa trên fixture. Add-on hiện tại vẫn là Android/Frida; cloud worker,
giao diện tải APK và kiểm thử container là công việc chưa hoàn thành.
Không thể dùng root để giải quyết phản hồi từ chối đăng nhập của cloud.

### Kết quả kiểm thử ban đầu

- Maven compile/test-compile: đạt.
- `ProtocolTest`: 10 kiểm tra đạt, gồm vector AES-GCM cố định, nonce prefix,
  từ chối tag bị sửa, envelope ngắn, canonical/MD5 swap và chữ ký phản hồi.
- Python unittest cho chuẩn bị tài nguyên: 4 kiểm tra đạt, gồm quyền file,
  allowlist ZIP, không ghi đè và dừng khi thiếu dữ liệu.
- Ruff check và format check cho Python mới: đạt.
- Native smoke test sau refactor: đạt, chỉ in độ dài/kết quả so sánh.
- 16 kiểm tra add-on hiện có: đạt bằng môi trường test sẵn có của dự án.
  Python hệ thống thiếu aiohttp/PyYAML; không sửa dependency hệ thống.
- Quét giá trị app ID/app secret trích từ APK trong các file nguồn mới: không có.
- Chưa kiểm thử đăng nhập thành công hoặc thiết bị thật; không phát hành phiên bản mới.
# Kiểm thử add-on 0.2.0 (05/09/2026)

Nguồn Java dùng chung đã chuyển vào `rangdong_key_helper/native-cloud`;
`poc/native-cloud/pom.xml` trỏ tới nguồn đó để tránh hai bản giao thức lệch nhau.
Đã chạy upload cặp APK thật qua `CloudClient`, chuẩn bị tài nguyên riêng,
khởi động worker với môi trường tối thiểu và tài khoản qua stdin, rồi gọi
`HelperController.cloud_scan`: nhận **9 key hợp lệ**, đi qua bước validate và
đến ranh giới bridge. Bridge trong bài kiểm thử này là đối tượng giả lập;
chưa chạy trên Supervisor/thiết bị LAN thật. Worker độc lập cũng trả 9 thiết bị.
Một lần gọi cloud trước đó lỗi chung; các lần kiểm chứng sau thành công,
không xác định được nguyên nhân lỗi tạm thời. Không tự retry khi lỗi cloud.
Kiểm thử tự động bảo đảm giao diện không trả key thô, account được xóa khỏi
dictionary, stdin không xuất hiện trong argv và worker không nhận Supervisor token.
