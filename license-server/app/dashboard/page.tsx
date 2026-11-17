"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import PasswordForm from "./password-form";

type Order = {id:string;order_code:string;amount:number;status:string;checkout_url:string|null;created_at:string};
type License = {id:string;plan_id:string;key:string;status:string;expires_at:string|null;bound:boolean};
type Dashboard = {user:{email:string;phone:string|null;admin:boolean};orders:Order[];licenses:License[];has_more:boolean;trial_claimed:boolean;has_pending_orders:boolean};
type Plan = {id:string;name:string;amount:number};
const messages:Record<string,string> = {
  invalid_credentials:"Email hoặc mật khẩu không đúng.", account_unavailable:"Email đã có tài khoản hoặc không thể đăng ký.",
  invalid_input:"Kiểm tra email và mật khẩu (12–128 ký tự).", rate_limited:"Thao tác quá nhanh. Vui lòng thử lại sau.",
  too_many_orders:"Có nhiều đơn chưa thanh toán. Hãy dùng đơn cũ.", transaction_conflict:"Yêu cầu bị trùng hoặc có thay đổi đồng thời. Hãy tải lại trang.",
  service_unavailable:"Dịch vụ chưa sẵn sàng. Không thanh toán lại nếu đã chuyển tiền.",
  incorrect_current_password:"Mật khẩu hiện tại không đúng.",password_mismatch:"Nhập lại mật khẩu mới chưa khớp.",password_unchanged:"Mật khẩu mới phải khác mật khẩu hiện tại.",login_required:"Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.",
};
const statuses:Record<string,string> = {active:"Có hiệu lực",locked:"Đã khóa",revoked:"Đã thu hồi",pending:"Chờ thanh toán",paid:"Đã thanh toán",cancelled:"Đã hủy",expired:"Hết hạn"};
async function api(path:string,data?:unknown,signal?:AbortSignal) {
  const controller=new AbortController(),abort=()=>controller.abort();
  const timer=setTimeout(abort,30000);signal?.addEventListener("abort",abort,{once:true});if(signal?.aborted)abort();
  try {
    const response=await fetch(`/api/${path}`,{method:data===undefined?"GET":"POST",headers:{"Content-Type":"application/json"},body:data===undefined?undefined:JSON.stringify(data),cache:"no-store",signal:controller.signal});
    const result=await response.json();if(!response.ok)throw new Error(result.error);return result;
  } finally {clearTimeout(timer);signal?.removeEventListener("abort",abort);}
}
function checkout(value:string|null) {
  if (!value) return undefined;
  try {const url=new URL(value);return url.protocol==="https:"&&(url.hostname==="pay.payos.vn"||url.hostname==="payos.vn")?url.href:undefined;}catch{return undefined;}
}
export default function DashboardPage() {
  const [page,setPage]=useState(0),[data,setData]=useState<Dashboard|null>(null),[plans,setPlans]=useState<Plan[]>([]);
  const [email,setEmail]=useState(""),[password,setPassword]=useState(""),[phone,setPhone]=useState("");
  const [mode,setMode]=useState<"login"|"register">("login"),[message,setMessage]=useState(""),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);
  const [loadError,setLoadError]=useState(false),[refreshing,setRefreshing]=useState(false);
  const activeRequest=useRef<AbortController|null>(null),mutating=useRef(false),phoneDirty=useRef(false);
  const refresh=useCallback(async(targetPage=page)=>{
    activeRequest.current?.abort();const controller=new AbortController();activeRequest.current=controller;setRefreshing(true);
    try {
      const result=await api(`dashboard?page=${targetPage}`,undefined,controller.signal);
      if(controller.signal.aborted)return;
      setData(result);if(!phoneDirty.current)setPhone(result.user.phone??"");setLoadError(false);
    } catch(error) {
      if(controller.signal.aborted)return;
      if((error as Error).message==="login_required"){setData(null);setLoadError(false);}else{setLoadError(true);throw error;}
    } finally {if(!controller.signal.aborted){setLoaded(true);setRefreshing(false);}}
  },[page]);
  useEffect(()=>{refresh().catch(()=>setMessage("Không tải được tài khoản. Hãy thử tải lại."));return()=>activeRequest.current?.abort();},[refresh]);
  useEffect(()=>{const controller=new AbortController();api("plans",undefined,controller.signal).then(result=>setPlans(result.plans)).catch(()=>{});return()=>controller.abort();},[]);
  useEffect(()=>{
    if(!data?.user.email || busy)return;
    let timer:ReturnType<typeof setTimeout>|undefined,stopped=false,generation=0;
    async function update(){
      if(stopped||document.visibilityState!=="visible"||!navigator.onLine)return;
      const current=++generation;
      try{await refresh();}catch{setMessage("Chưa cập nhật được dữ liệu. Kiểm tra kết nối hoặc bấm Tải lại.");}
      if(!stopped&&current===generation&&data?.has_pending_orders)timer=setTimeout(update,15000);
    }
    function resume(){clearTimeout(timer);generation++;if(document.visibilityState==="visible"&&navigator.onLine)void update();}
    if(data?.has_pending_orders)timer=setTimeout(update,15000);
    document.addEventListener("visibilitychange",resume);window.addEventListener("online",resume);
    return()=>{stopped=true;clearTimeout(timer);document.removeEventListener("visibilitychange",resume);window.removeEventListener("online",resume);};
  },[data?.user.email,data?.has_pending_orders,busy,refresh]);
  async function run(work:()=>Promise<void>){
    if(mutating.current)return false;
    mutating.current=true;activeRequest.current?.abort();setRefreshing(false);setBusy(true);setMessage("");
    try{await work();return true;}catch(error){if((error as Error).message==="login_required")setData(null);setMessage(messages[(error as Error).message]??"Thao tác chưa thành công. Vui lòng thử lại.");return false;}
    finally{mutating.current=false;setBusy(false);}
  }
  async function buy(plan:Plan) {
    if(plan.id==="trial"){await api("licenses/trial",{});await refresh();setMessage("Đã nhận key thử. Dùng 24 giờ từ lần kích hoạt đầu tiên trên Home Assistant.");return;}
    const storageKey=`rd-order:${data!.user.email}:${plan.id}`;
    let requestId=sessionStorage.getItem(storageKey);
    if(!requestId){requestId=crypto.randomUUID();sessionStorage.setItem(storageKey,requestId);}
    const result=await api("orders",{plan_id:plan.id,request_id:requestId});sessionStorage.removeItem(storageKey);
    const url=checkout(result.order.checkout_url);if(url)window.location.assign(url);else await refresh();
  }
  return <><div className="page-heading"><h1>Tài khoản & license</h1>{loaded&&<button className="secondary" disabled={busy||refreshing} onClick={()=>void run(()=>refresh())}>{refreshing?"Đang tải…":"Tải lại"}</button>}</div><p role="status" className="notice">{message}</p>{!loaded?<div className="card loading-state" role="status">Đang tải tài khoản…</div>:!data&&loadError?<section className="card"><h2>Chưa kết nối được</h2><p>Dữ liệu chưa tải xong. Hãy bấm Tải lại, không cần tạo tài khoản khác.</p></section>:!data?
    <section className="card"><h2>{mode==="login"?"Đăng nhập":"Tạo tài khoản"}</h2>
      <form onSubmit={event=>{event.preventDefault();run(async()=>{await api(`auth/${mode}`,{email,password,phone:mode==="register"?phone:undefined});setPassword("");phoneDirty.current=false;setPage(0);await refresh(0);});}}>
        <label>Email<input type="email" inputMode="email" autoCapitalize="none" spellCheck={false} autoComplete="email" required maxLength={254} value={email} onChange={event=>setEmail(event.target.value.trim().toLowerCase())}/></label>
        <label>Mật khẩu (12–128 ký tự)<input type="password" minLength={12} maxLength={128} autoComplete={mode==="login"?"current-password":"new-password"} required value={password} onChange={event=>setPassword(event.target.value)}/></label>
        {mode==="register"&&<label>Số điện thoại (không bắt buộc)<input autoComplete="tel" value={phone} maxLength={20} onChange={event=>setPhone(event.target.value)}/></label>}
        <button disabled={busy}>{mode==="login"?"Đăng nhập":"Tạo tài khoản"}</button>
        <button disabled={busy} type="button" className="secondary" onClick={()=>{setMode(mode==="login"?"register":"login");setMessage("");}}>{mode==="login"?"Chưa có tài khoản? Đăng ký":"Đã có tài khoản? Đăng nhập"}</button>
      </form><p className="muted">Chấp nhận email mọi nhà cung cấp, không cần mã OTP. Hãy lưu mật khẩu an toàn; chưa có khôi phục mật khẩu qua email.</p>
    </section>:<>
      <section className="card"><h2 className="account-email">{data.user.email}</h2><label>Số điện thoại (không bắt buộc)<input type="tel" autoComplete="tel" value={phone} disabled={busy} onChange={event=>{phoneDirty.current=true;setPhone(event.target.value);}} maxLength={20}/></label>
        <div className="account-actions"><button disabled={busy} onClick={()=>run(async()=>{await api("profile",{phone});phoneDirty.current=false;setMessage("Đã lưu.");})}>Lưu thông tin</button>
        <button disabled={busy} className="secondary" onClick={()=>run(async()=>{await api("auth/logout",{});setData(null);phoneDirty.current=false;setPage(0);setPassword("");})}>Đăng xuất</button>{data.user.admin&&<a href="/admin">Mở trang quản trị</a>}</div>
      </section>
      <PasswordForm busy={busy} onChange={values=>run(async()=>{await api("auth/password",values);setMessage("Đã đổi mật khẩu. Các phiên đăng nhập khác đã được đăng xuất.");})}/>
      <section><h2>Chọn gói license</h2><p>Một key cho 1 custom integration và 1 add-on trên cùng Home Assistant.</p>
        <div className="plan-grid">{plans.map(plan=><article className="card" key={plan.id}><h3>{plan.name} · {plan.amount===0?"Miễn phí":`${plan.amount.toLocaleString("vi-VN")}đ`}</h3>
          <p>{plan.id==="trial"?"24 giờ từ lần kích hoạt đầu tiên. Một lần cho mỗi tài khoản và installation; đổi email không cấp thêm lượt trên cùng installation.":plan.id==="monthly"?"30 ngày từ khi thanh toán được xác nhận. Không tự động trừ tiền gia hạn.":"Không có ngày hết hạn."}</p>
          <button disabled={busy||(plan.id==="trial"&&data.trial_claimed)} onClick={()=>run(()=>buy(plan))}>{plan.id==="trial"?(data.trial_claimed?"Đã nhận dùng thử":"Nhận key dùng thử"):"Tạo đơn & mở QR PayOS"}</button>
        </article>)}</div>
      </section>
      <section><h2>License của bạn</h2>{!data.licenses.length?<p>Chưa có key. Nhận dùng thử hoặc chọn gói trả phí ở trên.</p>:data.licenses.map(item=><article className="card" key={item.id}>
        <h3>{plans.find(plan=>plan.id===item.plan_id)?.name??item.plan_id}</h3>
        <p>{item.expires_at&&new Date(item.expires_at).getTime()<=Date.now()?"Đã hết hạn":statuses[item.status]??item.status} · {item.expires_at?new Date(item.expires_at).toLocaleString("vi-VN"):item.plan_id==="trial"?"24 giờ, chưa bắt đầu":"Vĩnh viễn"} · {item.bound?"Đã gắn Home Assistant":"Chưa kích hoạt"}</p>
        <code className="license">{item.key}</code><button className="secondary" onClick={()=>run(async()=>{await navigator.clipboard.writeText(item.key);setMessage("Đã sao chép key.");})}>Sao chép</button>
        <p className="muted">Dán cùng key vào custom/add-on trên một Home Assistant. Không chia sẻ key.</p>
      </article>)}</section>
      <section><h2>Lịch sử đơn hàng</h2>{data.orders.map(order=><article className="card" key={order.id}><h3>Đơn #{order.order_code}</h3><p>{order.amount.toLocaleString("vi-VN")}đ · {statuses[order.status]??order.status} · {new Date(order.created_at).toLocaleString("vi-VN")}</p>
        {order.status==="pending"&&checkout(order.checkout_url)&&<a className="button" href={checkout(order.checkout_url)}>Mở lại QR PayOS</a>}
        <button disabled={busy||order.status==="paid"} className="secondary" onClick={()=>run(async()=>{await api("orders/reconcile",{order_id:order.id});await refresh();setMessage("Đã đối soát trực tiếp với PayOS.");})}>Kiểm tra thanh toán</button>
      </article>)}</section>
      <div className="pager"><button disabled={busy||page===0} onClick={()=>setPage(page-1)}>Trang trước</button><span>Trang {page+1}</span><button disabled={busy||!data.has_more} onClick={()=>setPage(page+1)}>Trang sau</button></div>
    </>}</>;
}
