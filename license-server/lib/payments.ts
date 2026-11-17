import { PayOS } from "@payos/node";
import { randomUUID } from "node:crypto";
import type { PoolClient } from "pg";
import { database, transaction } from "./db";
import { encrypt, hash, newLicense, origin, PublicError, required } from "./security";
import { d1Enabled } from "./d1-client";
import { createOrderD1, settlePaymentD1 } from "./d1-operations";

export function payos() {
  return new PayOS({ clientId: required("PAYOS_CLIENT_ID"), apiKey: required("PAYOS_API_KEY"),
    checksumKey: required("PAYOS_CHECKSUM_KEY") });
}
export async function createOrder(userId: string, planId: string, requestId: string) {
  if (planId === "trial") throw new PublicError("use_trial_endpoint");
  const order = d1Enabled() ? await createOrderD1(userId,planId,requestId) : await transaction(async client => {
    await client.query("SELECT id FROM users WHERE id=$1 FOR UPDATE", [userId]);
    const existing = await client.query("SELECT * FROM orders WHERE user_id=$1 AND request_id=$2", [userId, requestId]);
    if (existing.rows[0]) return existing.rows[0];
    const pending = await client.query("SELECT count(*) FROM orders WHERE user_id=$1 AND status='pending' AND created_at>now()-interval '24 hours'", [userId]);
    if (Number(pending.rows[0].count) >= 5) throw new PublicError("too_many_orders", 429);
    const plan = (await client.query("SELECT * FROM plans WHERE id=$1 AND active=true AND amount>0", [planId])).rows[0];
    if (!plan) throw new PublicError("invalid_plan");
    return (await client.query(`INSERT INTO orders(id,user_id,plan_id,amount,duration_days,request_id)
      VALUES($1,$2,$3,$4,$5,$6) RETURNING *`, [randomUUID(), userId, planId, plan.amount, plan.duration_days, requestId])).rows[0];
  });
  if (order.checkout_url || order.status !== "pending") return order;
  const provider = payos();
  let payment;
  try {
    payment = await provider.paymentRequests.create({ orderCode: Number(order.order_code), amount: order.amount,
      description: `RD${order.order_code}`, returnUrl: `${origin()}/dashboard?order=${order.id}`,
      cancelUrl: `${origin()}/dashboard?order=${order.id}`, expiredAt: Math.floor(new Date(order.created_at).getTime()/1000)+3600 });
  } catch {
    const existing = await provider.paymentRequests.get(Number(order.order_code));
    if (existing.amount !== order.amount || Number(existing.orderCode) !== Number(order.order_code)) throw new PublicError("payment_mismatch", 502);
    await database().query("UPDATE orders SET payment_link_id=$1,checkout_url=$2 WHERE id=$3 AND status='pending'", [existing.id, `https://pay.payos.vn/web/${existing.id}`, order.id]);
    return (await database().query("SELECT * FROM orders WHERE id=$1", [order.id])).rows[0];
  }
  if (payment.amount !== order.amount || Number(payment.orderCode) !== Number(order.order_code)) throw new PublicError("payment_mismatch", 502);
  await database().query("UPDATE orders SET payment_link_id=$1,checkout_url=$2,qr_code=$3 WHERE id=$4 AND status='pending'",
    [payment.paymentLinkId, payment.checkoutUrl, payment.qrCode, order.id]);
  return (await database().query("SELECT * FROM orders WHERE id=$1", [order.id])).rows[0];
}

export type VerifiedPayment = { orderCode: number; amount: number; paymentLinkId: string; reference: string };

export async function settlePayment(client: PoolClient, payment: VerifiedPayment) {
  const order = (await client.query("SELECT * FROM orders WHERE order_code=$1 FOR UPDATE", [payment.orderCode])).rows[0];
  if (!order) return false;
  if (order.amount !== payment.amount || (order.payment_link_id && order.payment_link_id !== payment.paymentLinkId)) {
    throw new PublicError("payment_mismatch", 400);
  }
  const seen = (await client.query("SELECT order_id FROM payments WHERE reference=$1", [payment.reference])).rows[0];
  if (seen && seen.order_id !== order.id) throw new PublicError("payment_reference_conflict", 409);
  if (order.status === "paid") return true;
  await client.query("INSERT INTO payments(reference,order_id,payment_link_id,amount) VALUES($1,$2,$3,$4) ON CONFLICT(reference) DO NOTHING",
    [payment.reference, order.id, payment.paymentLinkId, payment.amount]);
  const check = (await client.query("SELECT order_id FROM payments WHERE reference=$1", [payment.reference])).rows[0];
  if (check.order_id !== order.id) throw new PublicError("payment_reference_conflict", 409);
  const key = newLicense();
  await client.query(`INSERT INTO licenses(id,user_id,plan_id,order_id,key_hash,key_cipher,expires_at)
    VALUES($1,$2,$3,$4,$5,$6,CASE WHEN $7::integer IS NULL THEN NULL ELSE now()+$7*interval '1 day' END)
    ON CONFLICT(order_id) DO NOTHING`, [randomUUID(), order.user_id, order.plan_id, order.id, hash(key), encrypt(key), order.duration_days]);
  await client.query("UPDATE orders SET status='paid',paid_at=now(),payment_link_id=$1 WHERE id=$2", [payment.paymentLinkId, order.id]);
  await client.query("INSERT INTO audit_log(id,action,target_id) VALUES($1,'payment.verified',$2)", [randomUUID(), order.id]);
  return true;
}

export async function receiveWebhook(payload: unknown) {
  const provider = payos();
  let event;
  try { event = await provider.webhooks.verify(payload as Parameters<typeof provider.webhooks.verify>[0]); }
  catch { throw new PublicError("invalid_webhook_signature", 400); }
  if (event.code !== "00") return;
  if (event.currency !== "VND" || !Number.isSafeInteger(event.orderCode) || !event.reference) throw new PublicError("invalid_payment");
  const known = await database().query("SELECT id,status,amount,payment_link_id FROM orders WHERE order_code=$1", [event.orderCode]);
  if (!known.rows[0]) return;
  if (known.rows[0].amount !== event.amount || (known.rows[0].payment_link_id && known.rows[0].payment_link_id !== event.paymentLinkId)) throw new PublicError("payment_mismatch", 409);
  if (known.rows[0].status === "paid") return;
  const info = await provider.paymentRequests.get(event.paymentLinkId);
  if (info.status !== "PAID" || info.id !== event.paymentLinkId || Number(info.orderCode) !== event.orderCode ||
      info.amount !== event.amount || info.amountPaid !== info.amount) throw new PublicError("payment_not_confirmed", 409);
  if (d1Enabled()) await settlePaymentD1(event);
  else await transaction(client => settlePayment(client, event));
}

export async function reconcileOrder(userId: string, orderId: string) {
  const order = (await database().query("SELECT * FROM orders WHERE id=$1 AND user_id=$2", [orderId, userId])).rows[0];
  if (!order) throw new PublicError("not_found", 404);
  if (order.status === "paid") return;
  const info = await payos().paymentRequests.get(Number(order.order_code));
  if (Number(info.orderCode) !== Number(order.order_code) || info.amount !== order.amount ||
      (order.payment_link_id && info.id !== order.payment_link_id)) throw new PublicError("payment_mismatch", 409);
  if (info.status === "PAID" && info.amountPaid === order.amount) {
    const transfer = info.transactions?.find(item => item.reference && item.amount === order.amount);
    if (!transfer) throw new PublicError("payment_reference_missing", 409);
    const payment = { orderCode: Number(order.order_code), amount: order.amount, paymentLinkId: info.id, reference: transfer.reference };
    if (d1Enabled()) await settlePaymentD1(payment);
    else await transaction(client => settlePayment(client, payment));
  } else if (["CANCELLED", "EXPIRED"].includes(info.status)) {
    await database().query("UPDATE orders SET status=$1 WHERE id=$2 AND status='pending'", [info.status.toLowerCase(), order.id]);
  }
}
