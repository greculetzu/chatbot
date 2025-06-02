import firebase_admin
from firebase_admin import credentials, firestore
import os

cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), "firebase_key.json"))
firebase_admin.initialize_app(cred)

db = firestore.client()

def save_order_to_firestore(order_data: dict):
    try:
        db.collection("orders").add(order_data)
        print("✅ Comandă salvată în Firestore!")
    except Exception as e:
        print("❌ Eroare la salvarea comenzii:", e)

def update_product_quantity(category, brand, quantity_to_deduct):
    try:
        query = db.collection("products") \
            .where("category", "==", category) \
            .where("brand", "==", brand)
        docs = list(query.stream())
        if docs:
            doc = docs[0]
            data = doc.to_dict()
            new_quantity = max(0, data["quantity"] - quantity_to_deduct)
            db.collection("products").document(doc.id).update({"quantity": new_quantity})
            print(f"🛒 Stoc actualizat: {data['quantity']} → {new_quantity}")
    except Exception as e:
        print("❌ Eroare la actualizarea stocului:", e)

def find_matching_products(category, brand, max_price, quantity):
    try:
        query = db.collection("products") \
            .where("category", "==", category) \
            .where("brand", "==", brand) \
            .where("price", "<=", float(max_price)) \
            .where("quantity", ">=", int(quantity))
        results = query.stream()
        return [doc.to_dict() for doc in results]
    except Exception as e:
        print("❌ Eroare la căutarea produselor:", e)
        return []

def find_alternative_products(category, brand, max_price):
    try:
        query = db.collection("products") \
            .where("category", "==", category) \
            .where("brand", "==", brand) \
            .where("quantity", ">", 0)
        results = query.stream()
        return [doc.to_dict() for doc in results]
    except Exception as e:
        print("❌ Eroare la căutarea alternativelor:", e)
        return []
