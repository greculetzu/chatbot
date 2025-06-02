from app.firebase_client import save_order_to_firestore, find_matching_products, update_product_stock
from app.lex_client import get_lex_response
from fastapi import WebSocket

async def chat_handler(websocket: WebSocket):
    await websocket.accept()
    session_slots = {}
    awaiting_confirmation = False
    pending_order = {}

    while True:
        try:
            user_msg = await websocket.receive_text()

            if awaiting_confirmation:
                if user_msg.lower() in ["yes", "y", "confirm"]:
                    update_product_stock(pending_order["category"], pending_order["brand"], pending_order["quantity"])
                    save_order_to_firestore(pending_order)
                    await websocket.send_text("✅ Thank you! Your order has been placed successfully.")
                else:
                    await websocket.send_text("❌ Order cancelled. Let me know if you'd like to start over.")
                awaiting_confirmation = False
                session_slots = {}
                pending_order = {}
                continue

            lex_response = get_lex_response(user_id="client1", message=user_msg)
            messages = lex_response.get("messages", [])
            reply = "\n".join([msg.get("content", "") for msg in messages]) or "(No reply)"

            intent = lex_response.get("sessionState", {}).get("intent", {}).get("name")
            slots = lex_response.get("sessionState", {}).get("intent", {}).get("slots", {})

            for slot_name, slot_data in slots.items():
                if slot_data and "value" in slot_data:
                    session_slots[slot_name] = slot_data["value"]["interpretedValue"]

            if intent == "CautaProdus":
                required_slots = ["category", "brand", "max_price", "quantity"]
                if all(slot in session_slots for slot in required_slots):
                    quantity_requested = int(session_slots["quantity"])
                    matching_products = find_matching_products(
                        session_slots["category"],
                        session_slots["brand"],
                        session_slots["max_price"]
                    )
                    if matching_products:
                        product = matching_products[0]
                        available_quantity = product.get("quantity", 0)
                        if available_quantity >= quantity_requested:
                            reply = f"We found {quantity_requested} {product['category'].lower()} from {product['brand'].lower()} at ${product['price']} each. Do you want to place the order?"
                        else:
                            reply = (
                                f"We only have {available_quantity} {product['category'].lower()} from {product['brand'].lower()} at ${product['price']} each. "
                                f"Would you like to order {available_quantity} instead?"
                            )
                            session_slots["quantity"] = str(available_quantity)  # Pregătim pentru confirmare
                    else:
                        reply = "Sorry, we couldn't find any product matching your preferences."

            elif intent == "PlaseazaComanda":
                required_slots = ["brand", "category", "quantity", "max_price", "customer_name", "delivery_method"]
                if all(slot in session_slots for slot in required_slots):
                    pending_order = {
                        "brand": session_slots["brand"],
                        "category": session_slots["category"],
                        "quantity": int(session_slots["quantity"]),
                        "max_price": session_slots["max_price"],
                        "customer_name": session_slots["customer_name"],
                        "delivery_method": session_slots["delivery_method"]
                    }
                    awaiting_confirmation = True
                    reply = (
                        f"Just to confirm: you're ordering {pending_order['quantity']} "
                        f"{pending_order['category']} from {pending_order['brand']} at max ${pending_order['max_price']}, "
                        f"delivered via {pending_order['delivery_method']} for {pending_order['customer_name']}. Is that correct?"
                    )

            await websocket.send_text(reply)

        except Exception as e:
            print("Conexiune WebSocket închisă sau eroare:", e)
            break
