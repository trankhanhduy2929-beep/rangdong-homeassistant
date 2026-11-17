import type { Metadata, Viewport } from "next";
import "./style.css";

export const metadata: Metadata = { title: "Rạng Đông — License", description: "Quản lý license Home Assistant" };
export const viewport: Viewport = { width:"device-width",initialScale:1,viewportFit:"cover",themeColor:"#146d52" };
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="vi"><body><a className="skip-link" href="#content">Đến nội dung chính</a><header><a href="/">RẠNG ĐÔNG · HOME ASSISTANT</a><nav aria-label="Điều hướng chính"><a href="/dashboard">Tài khoản</a><a href="/admin">Quản trị</a></nav></header><main id="content">{children}</main><footer>Tích hợp cộng đồng, không phải dịch vụ chính thức của nhà sản xuất. Không nhập mật khẩu tài khoản Rạng Đông tại đây.</footer></body></html>;
}
