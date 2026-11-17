"use client";
import { useState } from "react";

export default function PasswordForm({busy,onChange}:{busy:boolean;onChange:(values:{current_password:string;new_password:string;confirm_password:string})=>Promise<boolean>}) {
  const [current,setCurrent]=useState(""),[password,setPassword]=useState(""),[confirmation,setConfirmation]=useState(""),[visible,setVisible]=useState(false),[error,setError]=useState("");
  return <details className="card password-panel"><summary>Đổi mật khẩu</summary>
    <p className="muted">Cần mật khẩu hiện tại. Sau khi đổi, các phiên đăng nhập khác sẽ bị đăng xuất; key và đơn hàng giữ nguyên.</p>
    <form onSubmit={async event=>{
      event.preventDefault();setError("");
      if(password!==confirmation){setError("Nhập lại mật khẩu mới chưa khớp.");return;}
      if(password===current){setError("Mật khẩu mới phải khác mật khẩu hiện tại.");return;}
      if(await onChange({current_password:current,new_password:password,confirm_password:confirmation})) {setCurrent("");setPassword("");setConfirmation("");setVisible(false);}
    }}>
      <label>Mật khẩu hiện tại<input type={visible?"text":"password"} autoComplete="current-password" required minLength={12} maxLength={128} value={current} disabled={busy} onChange={event=>{setCurrent(event.target.value);setError("");}}/></label>
      <label>Mật khẩu mới<input type={visible?"text":"password"} autoComplete="new-password" required minLength={12} maxLength={128} value={password} disabled={busy} onChange={event=>{setPassword(event.target.value);setError("");}}/></label>
      <label>Nhập lại mật khẩu mới<input type={visible?"text":"password"} autoComplete="new-password" required minLength={12} maxLength={128} value={confirmation} disabled={busy} onChange={event=>{setConfirmation(event.target.value);setError("");}}/></label>
      <p className="muted">Dùng 12–128 ký tự, không dùng lại mật khẩu tài khoản Rạng Đông.</p>
      {error&&<p role="alert" className="form-error">{error}</p>}
      <div className="actions"><button disabled={busy}>Lưu mật khẩu mới</button><button type="button" className="secondary" aria-pressed={visible} onClick={()=>setVisible(!visible)}>{visible?"Ẩn mật khẩu":"Hiện mật khẩu"}</button></div>
    </form>
  </details>;
}
