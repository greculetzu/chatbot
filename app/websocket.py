from app.firebase_client import save_order_to_firestore, find_matching_products
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

            # Dacă așteptăm confirmarea finală
            if awaiting_confirmation:
                if user_msg.lower() in ["yes", "y", "confirm"]:
                    save_order_to_firestore(pending_order)
                    await websocket.send_text("✅ Thank you! Your order has been placed successfully.")
                else:
                    await websocket.send_text("❌ Order cancelled. Let me know if you'd like to start over.")
                awaiting_confirmation = False
                session_slots = {}
                pending_order = {}
                continue

            # Normal Lex flow
            lex_response = get_lex_response(user_id="client1", message=user_msg)
            messages = lex_response.get("messages", [])
            reply = "\n".join([msg.get("content", "") for msg in messages]) or "(No reply)"

            intent = lex_response.get("sessionState", {}).get("intent", {}).get("name")
            slots = lex_response.get("sessionState", {}).get("intent", {}).get("slots", {})

            for slot_name, slot_data in slots.items():
                if slot_data and "value" in slot_data:
                    session_slots[slot_name] = slot_data["value"]["interpretedValue"]

            if intent == "CautaProdus":
                # Nu căutăm până nu avem TOATE sloturile
                required_slots = ["category", "brand", "max_price", "quantity"]
                if all(slot in session_slots for slot in required_slots):
                    matching_products = find_matching_products(
                        category=session_slots["category"],
                        brand=session_slots["brand"],
                        max_price=session_slots["max_price"],
                        quantity=session_slots["quantity"]
                    )
                    if matching_products:
                        first = matching_products[0]
                        reply = f"We found a {first['category'].lower()} from {first['brand'].lower()} at ${first['price']}. Would you like to place the order?"
                    else:
                        reply = "Sorry, we couldn't find any product matching your preferences."

            elif intent == "PlaseazaComanda":
                required_slots = ["brand", "category", "quantity", "max_price", "customer_name", "delivery_method"]
                if all(slot in session_slots for slot in required_slots):
                    # Salvăm comanda în pending și cerem confirmarea
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
                        f"Just to confirm: you are ordering {pending_order['quantity']} "
                        f"{pending_order['category']} from {pending_order['brand']} "
                        f"at max ${pending_order['max_price']}, delivered via {pending_order['delivery_method']}, "
                        f"for {pending_order['customer_name']}. Is that correct?"
                    )

            await websocket.send_text(reply)

        except Exception as e:
            print("Conexiune WebSocket închisă sau eroare:", e)
            break
