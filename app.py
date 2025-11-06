
import pandas as pd
import requests
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from geopy.distance import geodesic
import streamlit as st
import openai
import folium
from streamlit_folium import st_folium

# ======================
# CONFIG
# ======================
MONGO_URI = "mongodb+srv://topicos_user:vt2GV4Q75YFJrVpR@puj-topicos-bd.m302xsg.mongodb.net/?retryWrites=true&w=majority&appName=puj-topicos-bd"
DATABASE_NAME = "restaurantes_bogota_db"
COLLECTION_NAME = "bogota_data"

GOOGLE_KEY = "AIzaSyAEsfwqS_pvzrJRFisamgisVvcVY6UUJ_s"
OPENAI_API_KEY = "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"

openai.api_key = OPENAI_API_KEY


# ======================
# FUNCTIONS
# ======================
def connect_mongo():
    try:
        client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        return client[DATABASE_NAME][COLLECTION_NAME]
    except Exception as e:
        st.error(f"Error conectando a MongoDB: {e}")
        return None


def read_mongo_data(col):
    data = list(col.find({}))
    for o in data:
        o["_id"] = str(o["_id"])
    return pd.DataFrame(data)


def get_coordinates(address):
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = requests.get(base_url, params={"address": address + ", Bogotá, Colombia", "key": GOOGLE_KEY}).json()

    if r["status"] == "OK":
        loc = r["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None


def calculate_distance(a, b):
    return geodesic(a, b).meters


def extract_coordinates(row):
    """Extrae coordenadas del formato que venga (ubicacion dict, lat/lng separados, etc)"""
    try:
        # Intenta primero con el campo 'ubicacion'
        if 'ubicacion' in row and isinstance(row['ubicacion'], dict):
            lat = row['ubicacion'].get('lat')
            lng = row['ubicacion'].get('lng')
            if lat is not None and lng is not None:
                return float(lat), float(lng)
        
        # Si no, intenta con campos separados
        if 'lat' in row and 'lng' in row:
            return float(row['lat']), float(row['lng'])
        
        if 'Latitud' in row and 'Longitud' in row:
            return float(row['Latitud']), float(row['Longitud'])
            
        return None, None
    except:
        return None, None


def filter_nearby(lat, lng, df, max_m=3000):
    distances = []
    valid_coords = []
    
    for idx, row in df.iterrows():
        rest_lat, rest_lng = extract_coordinates(row)
        
        if rest_lat is not None and rest_lng is not None:
            dist = calculate_distance((lat, lng), (rest_lat, rest_lng))
            distances.append(dist)
            valid_coords.append(True)
        else:
            distances.append(float('inf'))
            valid_coords.append(False)
    
    df["dist"] = distances
    df["valid_coords"] = valid_coords
    
    nearby = df[(df["dist"] <= max_m) & (df["valid_coords"] == True)].copy()
    return nearby.sort_values("dist")


def get_restaurant_name(r):
    """Obtiene el nombre del restaurante de diferentes campos posibles"""
    if 'nombre' in r:
        return r['nombre']
    if 'Nombre' in r:
        return r['Nombre']
    if 'name' in r:
        return r['name']
    return 'Sin nombre'


def get_restaurant_rating(r):
    """Obtiene el rating del restaurante"""
    if 'rating' in r:
        return r['rating']
    if 'Rating' in r:
        return r['Rating']
    return 'N/A'


def summarize_restaurants(rests):
    if len(rests) == 0:
        return "No se encontraron restaurantes cercanos."
    
    # Limitar a los 10 más cercanos
    rests = rests[:10]
    
    text = ""
    for r in rests:
        nombre = get_restaurant_name(r)
        rating = get_restaurant_rating(r)
        dist = round(r.get('dist', 0))
        
        text += f"\n{'='*60}\n"
        text += f"🍽️ {nombre}\n"
        text += f"⭐ Rating: {rating} | 📍 Distancia: {dist}m\n"
        
        # Dirección
        direccion = r.get('direccion') or r.get('Dirección') or 'N/A'
        text += f"📌 Dirección: {direccion}\n"
        
        # Horarios
        horarios = r.get('horarios', [])
        if horarios and len(horarios) > 0:
            text += f"🕒 Horarios: {horarios[0]}\n"
        
        # Estado de apertura
        if r.get('abierto_ahora'):
            text += "✅ Abierto ahora\n"
        
        # Tipos de establecimiento
        tipos = r.get('tipos', [])
        if tipos:
            tipos_filtrados = [t for t in tipos if t in ['restaurant', 'bar', 'cafe', 'bakery', 'meal_takeaway', 'meal_delivery']]
            if tipos_filtrados:
                text += f"🏷️ Tipo: {', '.join(tipos_filtrados)}\n"
        
        # Servicios
        servicios = r.get('servicios', {})
        servicios_disponibles = []
        if servicios:
            if servicios.get('dine_in'):
                servicios_disponibles.append("comer en el lugar")
            if servicios.get('takeout'):
                servicios_disponibles.append("para llevar")
            if servicios.get('delivery'):
                servicios_disponibles.append("domicilio")
            if servicios.get('serves_breakfast'):
                servicios_disponibles.append("desayuno")
            if servicios.get('serves_lunch'):
                servicios_disponibles.append("almuerzo")
            if servicios.get('serves_dinner'):
                servicios_disponibles.append("cena")
            if servicios.get('serves_vegetarian_food'):
                servicios_disponibles.append("comida vegetariana")
            if servicios.get('serves_brunch'):
                servicios_disponibles.append("brunch")
        
        if servicios_disponibles:
            text += f"🍴 Servicios: {', '.join(servicios_disponibles)}\n"
        
        # Pet friendly y vegano
        if r.get('pet_friendly'):
            text += "🐾 Pet Friendly\n"
        if r.get('vegano'):
            text += "🌱 Opciones veganas\n"
        
        # Resumen editorial
        editorial = r.get('editorial_summary', {})
        if editorial and editorial.get('overview'):
            text += f"📝 Descripción: {editorial['overview']}\n"
        
        # Reseñas destacadas
        resenas = r.get('reseñas', [])
        if resenas and isinstance(resenas, list) and len(resenas) > 0:
            text += f"💬 Reseña destacada ({resenas[0].get('rating', 'N/A')}⭐):\n"
            texto_resena = resenas[0].get('texto', '')
            if texto_resena:
                text += f"   \"{texto_resena[:200]}...\"\n"
        
        # Delivery disponible
        delivery = r.get('delivery', {})
        if delivery:
            apps = []
            if delivery.get('rappi'):
                apps.append("Rappi")
            if delivery.get('ubereats'):
                apps.append("Uber Eats")
            if apps:
                text += f"🚗 Delivery: {', '.join(apps)}\n"

    prompt = f"""
Eres un asistente experto en gastronomía de Bogotá. Analiza esta información detallada de restaurantes cercanos:

{text}

Genera un resumen profesional y atractivo que incluya:

1. **Resumen Ejecutivo**: Una descripción general de las opciones disponibles (tipos de comida, variedad de precios, ambiente)

2. **Top 3 Recomendaciones**: Los 3 mejores restaurantes con:
   - Por qué destacan (calidad, precio, ambiente, reseñas)
   - Qué tipo de comida ofrecen
   - Horarios importantes (si están abiertos ahora, horarios especiales)
   - Servicios destacados (delivery, pet friendly, vegano, etc.)

3. **Insights de Clientes**: Resume los comentarios más relevantes de las reseñas
   - Qué valoran los clientes
   - Puntos fuertes comunes
   - Recomendaciones específicas

4. **Consejos Prácticos**: 
   - Mejores opciones según horario (desayuno, almuerzo, cena)
   - Opciones especiales (vegetariano, pet friendly, delivery)
   - Distancia promedio

Mantén el tono amigable, informativo y útil. Máximo 400 palabras.
"""

    try:
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error al generar resumen con IA: {str(e)}\n\nRestaurantes encontrados:\n{text}"


# ======================
# STREAMLIT
# ======================
st.set_page_config(page_title="🍽️ Buscador de Restaurantes", layout="wide")
st.title("🍽️ Buscador Inteligente de Restaurantes")
st.markdown("Encuentra los mejores restaurantes cerca de tu ubicación")

col = connect_mongo()
if col is None:
    st.error("No se pudo conectar a la base de datos")
    st.stop()

df = read_mongo_data(col)

if df.empty:
    st.error("No se encontraron datos de restaurantes")
    st.stop()

# Input del usuario
addr = st.text_input("🔍 Ingresa tu ubicación:", placeholder="Ej: Calle 72 Carrera 5")

if addr:
    with st.spinner("Buscando tu ubicación..."):
        user_lat, user_lng = get_coordinates(addr)

    if user_lat and user_lng:
        st.success(f"✅ Ubicación encontrada")
        
        with st.spinner("Buscando restaurantes cercanos..."):
            nearby = filter_nearby(user_lat, user_lng, df, max_m=3000)

        if len(nearby) == 0:
            st.warning("⚠️ No se encontraron restaurantes en un radio de 3km")
        else:
            st.info(f"📍 Se encontraron {len(nearby)} restaurantes en un radio de 3km")
            
            # ---- MAPA ----
            st.subheader("🗺️ Mapa de Restaurantes")
            
            m = folium.Map(location=[user_lat, user_lng], zoom_start=14)

            # Marcador de usuario (ROJO)
            folium.Marker(
                [user_lat, user_lng],
                tooltip="📍 Tu ubicación",
                icon=folium.Icon(color="red", icon="home", prefix='fa')
            ).add_to(m)

            # Marcadores de restaurantes (AZUL)
            for idx, row in nearby.iterrows():
                rest_lat, rest_lng = extract_coordinates(row)
                
                if rest_lat and rest_lng:
                    nombre = get_restaurant_name(row)
                    rating = get_restaurant_rating(row)
                    dist = round(row.get('dist', 0))
                    
                    folium.Marker(
                        [rest_lat, rest_lng],
                        tooltip=f"{nombre}\nRating: {rating}\nDistancia: {dist}m",
                        popup=f"<b>{nombre}</b><br>Rating: {rating}<br>Distancia: {dist}m",
                        icon=folium.Icon(color="blue", icon="cutlery", prefix='fa')
                    ).add_to(m)

            st_folium(m, width=900, height=500)

            # ---- RESUMEN IA ----
            st.subheader("🤖 Resumen Inteligente")
            with st.spinner("Generando resumen con IA..."):
                summary = summarize_restaurants(nearby.to_dict(orient="records"))
            st.write(summary)

            # ---- TABLA ----
            st.subheader("📊 Lista de Restaurantes Cercanos")
            
            # Preparar datos para mostrar
            display_data = []
            for idx, row in nearby.iterrows():
                nombre = get_restaurant_name(row)
                rating = get_restaurant_rating(row)
                dist = round(row.get('dist', 0))
                direccion = row.get('direccion') or row.get('Dirección') or row.get('address') or 'N/A'
                
                display_data.append({
                    'Nombre': nombre,
                    'Rating': rating,
                    'Distancia (m)': dist,
                    'Dirección': direccion
                })
            
            display_df = pd.DataFrame(display_data)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.error("❌ No se pudo encontrar la ubicación. Intenta con una dirección más específica.")




















# import pandas as pd
# import requests
# from pymongo.mongo_client import MongoClient
# from pymongo.server_api import ServerApi
# from geopy.distance import geodesic
# import streamlit as st
# import openai
# import folium
# from streamlit_folium import st_folium

# # ======================
# # CONFIG
# # ======================
# MONGO_URI = "mongodb+srv://topicos_user:vt2GV4Q75YFJrVpR@puj-topicos-bd.m302xsg.mongodb.net/?retryWrites=true&w=majority&appName=puj-topicos-bd"
# DATABASE_NAME = "restaurantes_db"
# COLLECTION_NAME = "chapinero_data"

# GOOGLE_KEY = "AIzaSyAEsfwqS_pvzrJRFisamgisVvcVY6UUJ_s"
# OPENAI_API_KEY = "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"

# openai.api_key = OPENAI_API_KEY


# # ======================
# # FUNCTIONS
# # ======================
# def connect_mongo():
#     try:
#         client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
#         return client[DATABASE_NAME][COLLECTION_NAME]
#     except Exception as e:
#         st.error(f"Error conectando a MongoDB: {e}")
#         return None


# def read_mongo_data(col):
#     data = list(col.find({}))
#     for o in data:
#         o["_id"] = str(o["_id"])
#     return pd.DataFrame(data)


# def get_coordinates(address):
#     base_url = "https://maps.googleapis.com/maps/api/geocode/json"
#     r = requests.get(base_url, params={"address": address + ", Bogotá, Colombia", "key": GOOGLE_KEY}).json()

#     if r["status"] == "OK":
#         loc = r["results"][0]["geometry"]["location"]
#         return loc["lat"], loc["lng"]
#     return None, None


# def calculate_distance(a, b):
#     return geodesic(a, b).meters


# def extract_coordinates(row):
#     """Extrae coordenadas del formato que venga (ubicacion dict, lat/lng separados, etc)"""
#     try:
#         # Intenta primero con el campo 'ubicacion'
#         if 'ubicacion' in row and isinstance(row['ubicacion'], dict):
#             lat = row['ubicacion'].get('lat')
#             lng = row['ubicacion'].get('lng')
#             if lat is not None and lng is not None:
#                 return float(lat), float(lng)
        
#         # Si no, intenta con campos separados
#         if 'lat' in row and 'lng' in row:
#             return float(row['lat']), float(row['lng'])
        
#         if 'Latitud' in row and 'Longitud' in row:
#             return float(row['Latitud']), float(row['Longitud'])
            
#         return None, None
#     except:
#         return None, None


# def filter_nearby(lat, lng, df, max_m=10000):
#     distances = []
#     valid_coords = []
    
#     for idx, row in df.iterrows():
#         rest_lat, rest_lng = extract_coordinates(row)
        
#         if rest_lat is not None and rest_lng is not None:
#             dist = calculate_distance((lat, lng), (rest_lat, rest_lng))
#             distances.append(dist)
#             valid_coords.append(True)
#         else:
#             distances.append(float('inf'))
#             valid_coords.append(False)
    
#     df["dist"] = distances
#     df["valid_coords"] = valid_coords
    
#     nearby = df[(df["dist"] <= max_m) & (df["valid_coords"] == True)].copy()
#     return nearby.sort_values("dist")


# def get_restaurant_name(r):
#     """Obtiene el nombre del restaurante de diferentes campos posibles"""
#     if 'nombre' in r:
#         return r['nombre']
#     if 'Nombre' in r:
#         return r['Nombre']
#     if 'name' in r:
#         return r['name']
#     return 'Sin nombre'


# def get_restaurant_rating(r):
#     """Obtiene el rating del restaurante"""
#     if 'rating' in r:
#         return r['rating']
#     if 'Rating' in r:
#         return r['Rating']
#     return 'N/A'


# def summarize_restaurants(rests):
#     if len(rests) == 0:
#         return "No se encontraron restaurantes cercanos."
    
#     # Limitar a los 10 más cercanos
#     rests = rests[:10]
    
#     text = ""
#     for r in rests:
#         nombre = get_restaurant_name(r)
#         rating = get_restaurant_rating(r)
#         dist = round(r.get('dist', 0))
        
#         text += f"- {nombre} (Rating: {rating}, Distancia: {dist}m)\n"
        
#         # Buscar reseñas en diferentes campos
#         resenas = r.get('reseñas') or r.get('Reseñas') or r.get('reviews') or ''
#         if resenas and len(str(resenas)) > 10:
#             text += f"  Reseña: {str(resenas)[:150]}...\n"

#     prompt = f"""
# Analiza estos restaurantes cercanos y proporciona un resumen claro y útil:

# {text}

# Devuelve:
# 1. Resumen general de tipos de comida disponibles
# 2. Top 3 restaurantes recomendados con sus puntos fuertes
# 3. Comentarios destacados de clientes

# Mantén el resumen conciso y útil (máximo 300 palabras).
# """

#     try:
#         completion = openai.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[{"role": "user", "content": prompt}],
#             max_tokens=500,
#             temperature=0.7
#         )
#         return completion.choices[0].message.content
#     except Exception as e:
#         return f"Error al generar resumen con IA: {str(e)}\n\nRestaurantes encontrados:\n{text}"


# # ======================
# # STREAMLIT
# # ======================
# st.set_page_config(page_title="🍽️ Buscador de Restaurantes", layout="wide")
# st.title("🍽️ Buscador Inteligente de Restaurantes")
# st.markdown("Encuentra los mejores restaurantes cerca de tu ubicación")

# col = connect_mongo()
# if col is None:
#     st.error("No se pudo conectar a la base de datos")
#     st.stop()

# df = read_mongo_data(col)

# if df.empty:
#     st.error("No se encontraron datos de restaurantes")
#     st.stop()

# # Input del usuario
# addr = st.text_input("🔍 Ingresa tu ubicación:", placeholder="Ej: Calle 72 Carrera 5")

# if addr:
#     with st.spinner("Buscando tu ubicación..."):
#         user_lat, user_lng = get_coordinates(addr)

#     if user_lat and user_lng:
#         st.success(f"✅ Ubicación encontrada")
        
#         with st.spinner("Buscando restaurantes cercanos..."):
#             nearby = filter_nearby(user_lat, user_lng, df, max_m=10000)

#         if len(nearby) == 0:
#             st.warning("⚠️ No se encontraron restaurantes en un radio de 10km")
#         else:
#             st.info(f"📍 Se encontraron {len(nearby)} restaurantes en un radio de 10km")
            
#             # ---- MAPA ----
#             st.subheader("🗺️ Mapa de Restaurantes")
            
#             m = folium.Map(location=[user_lat, user_lng], zoom_start=14)

#             # Marcador de usuario (ROJO)
#             folium.Marker(
#                 [user_lat, user_lng],
#                 tooltip="📍 Tu ubicación",
#                 icon=folium.Icon(color="red", icon="home", prefix='fa')
#             ).add_to(m)

#             # Marcadores de restaurantes (AZUL)
#             for idx, row in nearby.iterrows():
#                 rest_lat, rest_lng = extract_coordinates(row)
                
#                 if rest_lat and rest_lng:
#                     nombre = get_restaurant_name(row)
#                     rating = get_restaurant_rating(row)
#                     dist = round(row.get('dist', 0))
                    
#                     folium.Marker(
#                         [rest_lat, rest_lng],
#                         tooltip=f"{nombre}\nRating: {rating}\nDistancia: {dist}m",
#                         popup=f"<b>{nombre}</b><br>Rating: {rating}<br>Distancia: {dist}m",
#                         icon=folium.Icon(color="blue", icon="cutlery", prefix='fa')
#                     ).add_to(m)

#             st_folium(m, width=900, height=500)

#             # ---- RESUMEN IA ----
#             st.subheader("🤖 Resumen Inteligente")
#             with st.spinner("Generando resumen con IA..."):
#                 summary = summarize_restaurants(nearby.to_dict(orient="records"))
#             st.write(summary)

#             # ---- TABLA ----
#             st.subheader("📊 Lista de Restaurantes Cercanos")
            
#             # Preparar datos para mostrar
#             display_data = []
#             for idx, row in nearby.iterrows():
#                 nombre = get_restaurant_name(row)
#                 rating = get_restaurant_rating(row)
#                 dist = round(row.get('dist', 0))
#                 direccion = row.get('direccion') or row.get('Dirección') or row.get('address') or 'N/A'
                
#                 display_data.append({
#                     'Nombre': nombre,
#                     'Rating': rating,
#                     'Distancia (m)': dist,
#                     'Dirección': direccion
#                 })
            
#             display_df = pd.DataFrame(display_data)
#             st.dataframe(display_df, use_container_width=True, hide_index=True)
#     else:
#         st.error("❌ No se pudo encontrar la ubicación. Intenta con una dirección más específica.")




