# Thông báo thành phần bên thứ ba

Mã nguồn do dự án Rạng Đông Key Helper tự phát triển được phát hành theo giấy
phép MIT của kho này. Helper đồng thời phân phối hoặc tải xuống các phần mềm
bên thứ ba sau:

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
