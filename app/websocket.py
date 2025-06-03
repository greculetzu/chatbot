from fastapi import WebSocket
from app.lex_client import get_lex_response
from app.firebase_client import (
    save_order_to_firestore,
    update_product_quantity,
    find_matching_products,
    find_alternative_products
)

async def chat_handler(websocket: WebSocket):
    await websocket.accept()
    session = {}
    stage = None

    while True:
        try:
            user_msg = await websocket.receive_text()

            if stage == "await_quantity":
                if user_msg.isdigit():
                    session["quantity"] = user_msg
                    stage = "await_delivery"
                    await websocket.send_text("How would you like the order delivered? For example, courier or pickup.")
                else:
                    await websocket.send_text("Please enter a valid number for quantity.")
                continue

            if stage == "await_delivery":
                session["delivery_method"] = user_msg
                stage = "await_name"
                await websocket.send_text("Can I have your name for the delivery?")
                continue

            if stage == "await_name":
                session["customer_name"] = user_msg
                stage = "await_final_confirm"
                await websocket.send_text(
                    f"Just to confirm: you're ordering {session['quantity']} {session['category']} from {session['brand']} at ${session['price']} each, "
                    f"delivered via {session['delivery_method']}, for {session['customer_name']}. Is that correct?"
                )
                continue

            if stage == "await_final_confirm":
                if user_msg.lower() in ["yes", "y"]:
                    save_order_to_firestore(session)
                    update_product_quantity(session["category"], session["brand"], int(session["quantity"]))
                    await websocket.send_text("✅ Thank you! Your order has been placed successfully.")
                else:
                    await websocket.send_text("❌ Order cancelled.")
                session.clear()
                stage = None
                continue

            # Obține răspuns de la Lex
            lex_response = get_lex_response(user_id="client1", message=user_msg)
            intent = lex_response.get("sessionState", {}).get("intent", {})
            slots = intent.get("slots", {})
            messages = lex_response.get("messages", [])
            response_text = "\n".join(msg.get("content", "") for msg in messages)

            if intent.get("name") == "CautaProdus":
                required = ["category", "brand", "max_price", "quantity"]
                slot_values = {}
                for key in required:
                    if key in slots and slots[key]:
                        slot_values[key] = slots[key]["value"]["interpretedValue"]

                if len(slot_values) == 4:
                    matches = find_matching_products(
                        slot_values["category"], slot_values["brand"],
                        slot_values["max_price"], slot_values["quantity"]
                    )
                    if matches:
                        product = matches[0]
                        session.update(slot_values)
                        session["price"] = product["price"]
                        stage = "await_delivery"
                        await websocket.send_text(
                            f"We found {session['quantity']} {session['category']} from {session['brand']} at ${session['price']}. "
                            f"How would you like the order delivered? For example, courier or pickup."
                        )
                        continue
                    else:
                        # caută alternative
                        alternatives = find_alternative_products(
                            slot_values["category"], slot_values["brand"], float(slot_values["max_price"])
                        )
                        if alternatives:
                            alt = alternatives[0]
                            session.update({
                                "category": alt["category"],
                                "brand": alt["brand"],
                                "price": alt["price"]
                            })
                            stage = "await_quantity"
                            await websocket.send_text(
                                f"Sorry, we couldn't find an exact match for {slot_values['quantity']} items under ${slot_values['max_price']}, "
                                f"but we do have {alt['quantity']} {alt['category']} from {alt['brand']} at ${alt['price']}. "
                                f"How many would you like to order?"
                            )
                            continue
                        else:
                            await websocket.send_text("Sorry, no alternative products available.")
                            continue

            await websocket.send_text(response_text)

        except Exception as e:
            print("Conexiune WebSocket închisă sau eroare:", e)
            break
