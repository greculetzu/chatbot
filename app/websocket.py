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
    pending_order = {}
    alternative_product = None

    while True:
        try:
            user_msg = await websocket.receive_text()

            # ✅ CONFIRMARE FINALĂ
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
                    await websocket.send_text("❌ Order cancelled. Let me know if you'd like to start over.")
                awaiting_confirmation = False
                session_slots.clear()
                pending_order.clear()
                continue

            # ✅ Cantitate alternativă
            if awaiting_quantity_for_alternative:
                try:
                    quantity = int(user_msg)
                    pending_order["quantity"] = str(quantity)
                    awaiting_quantity_for_alternative = False
                    reply = "Ok, let's finish your order. I just need a few more details. How would you like the order delivered? For example, courier or pickup."
                    await websocket.send_text(reply)
                    continue
                except ValueError:
                    await websocket.send_text("Please enter a valid number for quantity.")
                    continue

            # ✅ Normal flow Lex
            lex_response = get_lex_response(user_id="client1", message=user_msg)
            messages = lex_response.get("messages", [])
            reply = "\n".join([msg.get("content", "") for msg in messages]) or "(No reply)"

            intent = lex_response.get("sessionState", {}).get("intent", {}).get("name")
            slots = lex_response.get("sessionState", {}).get("intent", {}).get("slots", {})

            for slot_name, slot_data in slots.items():
                if slot_data and "value" in slot_data:
                    session_slots[slot_name] = slot_data["value"]["interpretedValue"]

            # ✅ Intentul CautaProdus
            if intent == "CautaProdus":
                required_slots = ["category", "brand", "max_price", "quantity"]
                if all(slot in session_slots for slot in required_slots):
                    products = find_matching_products(
                        session_slots["category"],
                        session_slots["brand"],
                        session_slots["max_price"],
                        session_slots["quantity"]
                    )
                    if products:
                        first = products[0]
                        reply = (
                            f"We found {session_slots['quantity']} {first['category'].lower()} from {first['brand'].lower()} "
                            f"at ${first['price']}. Would you like to place the order?"
                        )
                        pending_order = {
                            "brand": session_slots["brand"],
                            "category": session_slots["category"],
                            "quantity": session_slots["quantity"],
                            "max_price": session_slots["max_price"]
                        }
                        awaiting_confirmation = True
                    else:
                        # ✅ Căutăm alternative
                        alternatives = find_alternative_products(
                            session_slots["category"],
                            session_slots["brand"]
                        )
                        if alternatives:
                            best = alternatives[0]
                            alternative_product = best
                            pending_order = {
                                "brand": best["brand"],
                                "category": best["category"],
                                "price": best["price"]
                            }
                            reply = (
                                f"Sorry, we couldn't find an exact match for {session_slots['quantity']} items under ${session_slots['max_price']}, "
                                f"but we do have {best['quantity']} {best['category']} from {best['brand']} at ${best['price']}. Would you like that instead?"
                            )
                            session_slots["category"] = best["category"]
                            session_slots["brand"] = best["brand"]
                            session_slots["max_price"] = str(best["price"])
                        else:
                            reply = "Sorry, we couldn't find anything matching. Would you like to try a different category or brand?"

            elif intent == "PlaseazaComanda":
                required = ["brand", "category", "quantity", "max_price", "customer_name", "delivery_method"]
                if all(slot in session_slots for slot in required):
                    pending_order = {
                        "brand": session_slots["brand"],
                        "category": session_slots["category"],
                        "quantity": session_slots["quantity"],
                        "max_price": session_slots["max_price"],
                        "customer_name": session_slots["customer_name"],
                        "delivery_method": session_slots["delivery_method"]
                    }
                    awaiting_confirmation = True
                    reply = (
                        f"Just to confirm: you're ordering {pending_order['quantity']} {pending_order['category']} from {pending_order['brand']} "
                        f"at max ${pending_order['max_price']}, delivered via {pending_order['delivery_method']}, for {pending_order['customer_name']}. "
                        f"Is that correct?"
                    )

            # ✅ dacă tocmai am acceptat alternativa, cerem cantitatea
            if alternative_product and user_msg.lower() in ["yes", "y", "confirm"]:
                awaiting_quantity_for_alternative = True
                alternative_product = None
                await websocket.send_text("How many would you like to order?")
                continue

            await websocket.send_text(reply)

        except Exception as e:
            print("Conexiune WebSocket închisă sau eroare:", e)
            break
