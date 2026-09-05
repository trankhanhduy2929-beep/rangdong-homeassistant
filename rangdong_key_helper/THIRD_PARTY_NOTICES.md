# Thông báo thành phần bên thứ ba

Mã nguồn do dự án Rạng Đông Key Helper tự phát triển được phát hành theo giấy
phép MIT của kho này. Helper đồng thời phân phối hoặc tải xuống các phần mềm
bên thứ ba sau:

## Worker cloud từ 0.2.0

- Unidbg Android và backend Unicorn2 **0.9.8**: mã Java theo Apache-2.0;
  nguồn `https://github.com/zhkl0228/unidbg/tree/v0.9.8`.
- Backend dùng Unicorn Engine (GPL-2.0); nhánh nguồn của nhà cung cấp:
  `https://github.com/zhkl0228/unicorn/tree/unicorn2`. Hướng dẫn dựng JNI nằm
  trong `backend/unicorn2` của mã nguồn Unidbg. Giấy phép và thông báo của
  các thành phần nhúng vẫn áp dụng, không bị thay bằng MIT của helper.
- Fastjson **1.2.83** (Apache-2.0), SLF4J **2.0.13** (MIT), cùng phụ thuộc
  chuyển tiếp được Maven giải quyết từ `native-cloud/pom.xml`. Các JAR giữ
  nguyên metadata/giấy phép của nhà cung cấp trong `META-INF`.
- OpenJDK 21 từ Debian (GPL-2.0 với Classpath exception khi áp dụng); xem
  thông báo gói tại `/usr/share/doc` trong image. Maven/Temurin chỉ dùng ở
  giai đoạn build, không sao chép nguyên môi trường Maven vào image chạy.

Từ 0.2.1, cặp APK Rạng Đông 5.7.2 do chủ dự án cung cấp được giữ nguyên trong
bản tài nguyên `native-resources-5.7.2` và tải vào image lúc build. Không đưa
binary vào lịch sử Git; chữ ký/checksum APK không thay đổi. APK và thư viện
của hãng không thuộc giấy phép MIT của helper; mọi quyền của nhà sản xuất
vẫn được giữ nguyên. Đây không phải ứng dụng/tích hợp chính thức của Rạng Đông.
Không có tài khoản, mật khẩu đăng nhập, phiên hoặc local key thiết bị trong
các APK tài nguyên này. Image không chứa dữ liệu của tài khoản thử nghiệm.

## Frida Java bridge 7.0.13

Agent đã biên dịch tại
`rootfs/app/rangdong_helper/frida_agent.js` chứa nguyên gói npm
`frida-java-bridge`, phiên bản `7.0.13`.

- Mã nguồn dự án gốc: `https://github.com/frida/frida-java-bridge/tree/v7.0.13`
- Nguồn gói: `https://registry.npmjs.org/frida-java-bridge/-/frida-java-bridge-7.0.13.tgz`
- Khai báo giấy phép của dự án gốc: `LGPL-2.0 WITH WxWindows-exception-3.1`

Phần phụ thuộc (dependency) chính xác được ghim trong `agent/package-lock.json`.
Phiên bản phù hợp để chỉnh sửa có tại mã nguồn dự án gốc ở trên và có thể đóng
gói lại bằng:

```sh
cd rangdong_key_helper/agent
npm ci
npm run build
```

## Frida 17.17.0

Container cài thư viện liên kết Python của Frida phiên bản `17.17.0`. Trong một thao tác
đã được người dùng cho phép, helper có thể tải Frida server chính thức phiên bản
`17.17.0` tương ứng với kiến trúc Android. Tệp tải xuống được kiểm tra bằng
SHA-256 đã ghim trước khi sử dụng.

- Mã nguồn dự án gốc: `https://github.com/frida/frida/tree/17.17.0`
- Các tệp phát hành: `https://github.com/frida/frida/releases/tag/17.17.0`
- Giấy phép: wxWindows Library Licence, phiên bản 3.1

Nội dung giấy phép GNU Library General Public License áp dụng và ngoại lệ
wxWindows được sao chép trong `LICENSE.frida.txt`. Thông báo này không thay đổi
các quyền được cấp theo giấy phép của chủ sở hữu bản quyền tương ứng.
