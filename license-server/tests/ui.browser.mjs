import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||"playwright");
const base=process.env.BROWSER_BASE_URL||"http://127.0.0.1:3108";
const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE_PATH});
const plans=[{id:"trial",name:"Dùng thử 1 ngày",amount:0},{id:"monthly",name:"1 tháng (30 ngày)",amount:50000},{id:"lifetime",name:"Vĩnh viễn",amount:200000}];
const dashboard={user:{email:"a-long-customer-email-for-mobile@example.invalid",phone:"0900000000",admin:true},orders:[],licenses:[{id:"test-license",plan_id:"lifetime",key:"RD-"+"A".repeat(48),status:"active",expires_at:null,bound:true}],has_more:true,trial_claimed:false,has_pending_orders:false};
const artifact=process.env.BROWSER_ARTIFACT_DIR||"/tmp/rd-web-mobile";
await mkdir(artifact,{recursive:true});
try {
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});
  const page=await context.newPage();const errors=[];page.on("pageerror",error=>errors.push(error.message));
  const calls={dashboard:0,plans:0,password:0};let loggedIn=true,forbidden=false,passwordPayload;
  await page.route("**/api/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==="/api/plans"){calls.plans++;return route.fulfill({json:{plans}});}
    if(path==="/api/dashboard"){calls.dashboard++;return route.fulfill({status:loggedIn?200:401,json:loggedIn?dashboard:{error:"login_required"}});}
    if(path==="/api/auth/password"){calls.password++;passwordPayload=route.request().postDataJSON();return route.fulfill({json:{success:true}});}
    if(path==="/api/auth/logout"){loggedIn=false;return route.fulfill({json:{success:true}});}
    if(path==="/api/admin/overview")return route.fulfill({status:forbidden?403:200,json:forbidden?{error:"forbidden"}:{users:[{id:"test-user",email:dashboard.user.email,phone:"0900000000",created_at:"2026-09-05T12:00:00.000Z"}],orders:[{id:"long-order-id",email:dashboard.user.email,status:"pending",amount:50000}],licenses:[],audit:[{id:"test-audit",action:"account.password_changed",target_id:"test-user"}],revenue:{revenue:0,paid_orders:0},totals:{users:1,orders:1,licenses:0}}});
    return route.fulfill({json:{success:true}});
  });
  async function fits(width){await page.setViewportSize({width,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),`Horizontal overflow at ${width}px`);}
  await page.goto(base+"/dashboard");await page.getByText(dashboard.user.email,{exact:true}).waitFor();
  await page.getByRole("button",{name:"Đã nhận dùng thử",exact:true}).count();
  await page.clock.install();
  const idle=calls.dashboard;await page.clock.runFor(45000);assert.equal(calls.dashboard,idle,"Idle dashboard must not poll");
  const phone=page.getByLabel("Số điện thoại (không bắt buộc)");await phone.fill("0999999999");
  await page.getByRole("button",{name:"Tải lại",exact:true}).click();await page.getByRole("button",{name:"Tải lại",exact:true}).waitFor();assert.equal(await phone.inputValue(),"0999999999");
  await page.getByText("Đổi mật khẩu",{exact:true}).click();
  const current=page.getByLabel("Mật khẩu hiện tại",{exact:true}),password=page.getByLabel("Mật khẩu mới",{exact:true}),confirmation=page.getByLabel("Nhập lại mật khẩu mới",{exact:true});
  await current.fill("current-test-password");await password.fill("new-password-12345");await confirmation.fill("different-password");
  await page.getByRole("button",{name:"Lưu mật khẩu mới"}).click();assert.equal(calls.password,0);await page.locator(".form-error").waitFor();
  await confirmation.fill("new-password-12345");await page.getByRole("button",{name:"Hiện mật khẩu",exact:true}).click();assert.equal(await current.getAttribute("type"),"text");
  for(const width of [320,390,768,1280])await fits(width);
  await fits(390);await page.screenshot({path:artifact+"/dashboard-mobile.png",fullPage:true});
  await page.getByRole("button",{name:"Lưu mật khẩu mới"}).click();await page.getByText("Đã đổi mật khẩu. Các phiên đăng nhập khác đã được đăng xuất.",{exact:true}).waitFor();
  assert.equal(calls.password,1);assert.equal(passwordPayload.new_password,"new-password-12345");assert.equal(await current.inputValue(),"");assert.equal(await password.inputValue(),"");
  const planCalls=calls.plans;await page.getByRole("button",{name:"Trang sau",exact:true}).click();await page.getByText("Trang 2",{exact:true}).waitFor();assert.equal(calls.plans,planCalls,"Pagination must not reload plans");
  dashboard.has_pending_orders=true;await page.getByRole("button",{name:"Tải lại",exact:true}).click();await page.getByRole("button",{name:"Tải lại",exact:true}).waitFor();
  await page.evaluate(()=>{Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"hidden"});document.dispatchEvent(new Event("visibilitychange"));});
  const hidden=calls.dashboard;await page.clock.runFor(45000);assert.equal(calls.dashboard,hidden,"Hidden tabs must not poll");
  await page.evaluate(()=>{Object.defineProperty(document,"visibilityState",{configurable:true,get:()=>"visible"});document.dispatchEvent(new Event("visibilitychange"));});
  await page.waitForFunction(()=>document.querySelector(".page-heading button")?.textContent==="Tải lại");
  const resumed=calls.dashboard;await page.clock.runFor(16000);await page.waitForTimeout(50);assert.ok(calls.dashboard>resumed,"Pending orders should refresh when visible");
  await page.goto(base+"/admin");await page.getByRole("heading",{name:"Người dùng",exact:true}).waitFor();
  for(const width of [320,390,768,1280])await fits(width);
  await fits(390);await page.screenshot({path:artifact+"/admin-mobile.png",fullPage:true});
  forbidden=true;await page.getByRole("button",{name:"Tải lại",exact:true}).click();await page.getByText("Cần đăng nhập tài khoản quản trị.",{exact:true}).waitFor();assert.equal(await page.getByRole("heading",{name:"Người dùng",exact:true}).count(),0);
  loggedIn=false;await page.goto(base+"/dashboard");await page.getByRole("heading",{name:"Đăng nhập",exact:true}).waitFor();
  for(const width of [320,390])await fits(width);
  assert.equal(await page.getByLabel("Email",{exact:true}).evaluate(element=>getComputedStyle(element).fontSize),"16px");
  assert.deepEqual(errors,[]);await context.close();
  console.log("Browser tests passed: password form, mobile 320/390/768/1280, no idle/hidden polling, pending refresh, draft preservation, admin expiry.");
}finally{await browser.close();}
