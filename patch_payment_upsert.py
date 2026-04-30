import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

MARKER = '            new_delivery_status = payload.get("delivery_status")\n            previous_delivery_status = str(existing_booking.get("delivery_status", "") or "")\n            transitioned = bool(new_delivery_status) and new_delivery_status != previous_delivery_status'

PAYMENT_BLOCK = '''            # --- Payment upsert after booking update ---
            try:
                final_status = payload.get("status") or existing_booking.get("status", "Pending")
                payment_status_map = {
                    "Completed": "Paid",
                    "Cancelled": "Cancelled",
                    "Pending": "Pending",
                    "In Progress": "Pending",
                }
                payment_status = payment_status_map.get(final_status, "Pending")
                amount = float(
                    payload.get("total_price")
                    or existing_booking.get("total_price")
                    or existing_booking.get("total_amount")
                    or 0
                )
                customer_name = (
                    payload.get("full_name")
                    or existing_booking.get("full_name")
                    or "FreshWash Customer"
                )
                payment_method = existing_booking.get("payment_method") or "Unspecified"
                proof_of_payment = (
                    existing_booking.get("payment_proof")
                    or existing_booking.get("proof_of_payment")
                    or ""
                )
                payment_payload = {
                    "booking_id": booking_id,
                    "customer_name": customer_name,
                    "payment_method": payment_method,
                    "amount": amount,
                    "payment_status": payment_status,
                    "proof_of_payment": proof_of_payment,
                    "date": datetime.now(timezone.utc).isoformat(),
                }
                existing_payment_res = (
                    client.table("payments")
                    .select("id")
                    .eq("booking_id", booking_id)
                    .limit(1)
                    .execute()
                )
                existing_payment = (
                    (existing_payment_res.data or [{}])[0]
                    if existing_payment_res
                    else {}
                )
                if existing_payment.get("id"):
                    client.table("payments").update(payment_payload).eq("booking_id", booking_id).execute()
                else:
                    client.table("payments").insert(payment_payload).execute()
            except Exception as pay_exc:
                log_exception("payment upsert after booking edit failed", pay_exc, booking_id=booking_id)
            # --- End payment upsert ---

'''

if MARKER in content:
    content = content.replace(MARKER, PAYMENT_BLOCK + MARKER)
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS: Payment upsert block inserted.")
else:
    print("ERROR: Marker not found. No changes made.")
