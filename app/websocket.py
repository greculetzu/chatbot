from app.firebase_client import (
    save_order_to_firestore,
    update_product_quantity,
    find_matching_products,
    find_alternative_products
)
from app.lex_client import get_lex_response
from fastapi import WebSocket

async def chat_handler(websocket: WebSocket):
    await websocket.accept()
    session_slots = {}
    awaiting_confirmation = False
    awaiting_quantity_for_alternative = False
    awaiting_delivery = False
    awaiting_name = False
    pending_order = {}
    alternative_product = None

    while True:
        try:
            user_msg = await websocket.receive_text()

            # ✅ Confirmare finală
            if awaiting_confirmation:
                if user_msg.lower() in ["yes", "y", "confirm"]:
                    save_order_to_firestore(pending_order)
                    update_product_quantity(
                        pending_order["category"],
                        pending_order["brand"],
                        int(pending_order["quantity"])
                    )
                    await websocket.send_text("✅ Thank you! Your order has been placed successfully.")
                else:
                    await websocket.send_text("❌ Order cancelled.")
                awaiting_confirmation = False
                awaiting_delivery = False
                awaiting_name = False
                session_slots.clear()
                pending_order.clear()
                continue

            # ✅ Cantitate pentru produs alternativ
            if awaiting_quantity_for_alternative:
                if user_msg.isdigit():
                    pending_order["quantity"] = user_msg
                    awaiting_quantity_for_alternative = False
                    awaiting_delivery = True
                    await websocket.send_text("How would you like the order delivered? For example, courier or pickup.")
                    continue
                else:
                    await websocket.send_text("Please enter a valid number.")
                    continue

            # ✅ Metodă de livrare
            if awaiting_delivery:
                pending_order["delivery_method"] = user_msg
                awaiting_delivery = False
                awaiting_name = True
                await websocket.send_text("Can I have your name for the delivery?")
                continue

            # ✅ Nume client
            if awaiting_name:
                pending_order["customer_name"] = user_msg
                awaiting_name = False
                awaiting_confirmation = True
                reply = (
                    f"Just to confirm: you're ordering {pending_order['quantity']} {pending_order['category']} "
                    f"from {pending_order['brand']} at ${pending_order['price']} each, delivered via "
                    f"{pending_order['delivery_method']}, for {pending_order['customer_name']}. Is that correct?"
                )
                await websocket.send_text(reply)
                continue

            # ✅ Normal Lex flow
            lex_response = get_lex_response(user_id="client1", message=user_msg)
            messages = lex_response.get("messages", [])
            reply = "\n".join([msg.get("content", "") for msg in messages]) or "(No reply)"

            intent = lex_response.get("sessionState", {}).get("intent", {}).get("name")
            slots = lex_response.get("sessionState", {}).get("intent", {}).get("slots", {})

            for slot_name, slot_data in slots.items():
                if slot_data and "value" in slot_data:
                    session_slots[slot_name] = slot_data["value"]["interpretedValue"]

            # ✅ Intent CautaProdus
            if intent == "CautaProdus":
                required = ["category", "brand", "max_price", "quantity"]
                if all(slot in session_slots for slot in required):
                    category = session_slots["category"]
                    brand = session_slots["brand"]
                    max_price = session_slots["max_price"]
                    quantity = session_slots["quantity"]

                    products = find_matching_products(category, brand, max_price, quantity)
                    if products:
                        first = products[0]
                        pending_order = {
                            "brand": brand,
                            "category": category,
                            "quantity": quantity,
                            "price": first["price"]
                        }
                        reply = (
                            f"We found {quantity} {category} from {brand} at ${first['price']}. "
                            "Would you like to place the order?"
                        )
                        awaiting_delivery = True
                    else:
                        alternatives = find_alternative_products(category, brand, max_price)
                        if alternatives:
                            best = alternatives[0]
                            alternative_product = best
                            pending_order = {
                                "brand": best["brand"],
                                "category": best["category"],
                                "price": best["price"]
                            }
                            reply = (
                                f"Sorry, we couldn't find an exact match for {quantity} items under ${max_price}, "
                                f"but we do have {best['quantity']} {best['category']} from {best['brand']} "
                                f"at ${best['price']}. Would you like that instead?"
                            )
                        else:
                            reply = "Sorry, no alternative products available."

            # ✅ Acceptare sugestie alternativă
            if alternative_product and user_msg.lower() in ["yes", "y", "confirm"]:
                awaiting_quantity_for_alternative = True
                alternative_product = None
                await websocket.send_text("How many would you like to order?")
                continue

            await websocket.send_text(reply)

        except Exception as e:
            print("❌ Eroare WebSocket:", e)
            break
