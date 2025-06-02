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

def find_matching_products(category, brand, max_price, quantity):
    try:
        query = db.collection("products")
        if category:
            query = query.where("category", "==", category)
        if brand:
            query = query.where("brand", "==", brand)
        if max_price:
            query = query.where("price", "<=", float(max_price))
        if quantity:
            query = query.where("quantity", ">=", int(quantity))
        results = query.stream()
        return [doc.to_dict() for doc in results]
    except Exception as e:
        print("❌ Eroare la căutarea produselor:", e)
        return []
