import pandas as pd
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import json

# --- CONFIGURACIÓN ---
MONGO_URI = "mongodb+srv://topicos_user:vt2GV4Q75YFJrVpR@puj-topicos-bd.m302xsg.mongodb.net/?retryWrites=true&w=majority&appName=puj-topicos-bd"

JSON_FILE = "restaurantes_bogota_completo.json"    # ✅ nuevo archivo
DATABASE_NAME = "restaurantes_bogota_db"           # ✅ nueva base
COLLECTION_NAME = "bogota_data"                    # ✅ nueva colección

# --- 1. CONEXIÓN ---
print("--- 1. INICIANDO CONEXIÓN A MONGODB ATLAS ---")

try:
    fixed_uri = MONGO_URI.replace('mongodb-srv://', 'mongodb+srv://')
    client = MongoClient(fixed_uri, server_api=ServerApi('1'))

    db_names = client.list_database_names()

    if DATABASE_NAME in db_names:
        print(f"✅ La base de datos '{DATABASE_NAME}' ya existe.")
    else:
        print(f"🔄 La base de datos '{DATABASE_NAME}' no existe. Se creará cuando se inserten datos.")

    db = client[DATABASE_NAME]
    collection_names = db.list_collection_names()

    if COLLECTION_NAME in collection_names:
        print(f"✅ La colección '{COLLECTION_NAME}' ya existe.")
    else:
        print(f"🔄 La colección '{COLLECTION_NAME}' no existe. Se creará cuando se inserten datos.")

except Exception as e:
    print(f"❌ Error al conectar a MongoDB: {e}")
    exit()

# --- 2. LEER JSON Y SUBIR ---
print("\n--- 2. SUBIENDO DATOS A MONGODB ---")

try:
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    collection = db[COLLECTION_NAME]

    result = collection.insert_many(data)

    print(f"✅ {len(result.inserted_ids)} documentos insertados en '{COLLECTION_NAME}'.")

except Exception as e:
    print(f"❌ Error leyendo o insertando JSON: {e}")
    exit()

# --- 3. LECTURA DESDE ATLAS ---
print("\n--- 3. LEYENDO DATOS ---")

try:
    cursor = collection.find({})
    df = pd.DataFrame(list(cursor))

    print(f"\n🚀 Total documentos leídos: {len(df)}")
    print(df.head())
    print(f"\nColumnas: {df.columns.tolist()}")

except Exception as e:
    print(f"❌ Error leyendo desde MongoDB: {e}")

finally:
    client.close()
    print("\n🔌 Conexión cerrada.")
