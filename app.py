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
# Cargar secrets de forma segura (funciona local y en Streamlit Cloud)
try:
    MONGO_URI = st.secrets["MONGO_URI"]
    GOOGLE_KEY = st.secrets["GOOGLE_KEY"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    # Fallback para desarrollo local sin secrets
    MONGO_URI = "mongodb+srv://topicos_user:vt2GV4Q75YFJrVpR@puj-topicos-bd.m302xsg.mongodb.net/?retryWrites=true&w=majority&appName=puj-topicos-bd"
    GOOGLE_KEY = "AIzaSyAEsfwqS_pvzrJRFisamgisVvcVY6UUJ_s"
    OPENAI_API_KEY = "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"

DATABASE_NAME = "restaurantes_bogota_db"
COLLECTION_NAME = "bogota_data"

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


def filter_nearby(lat, lng, df, max_m=10000):
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
    
    # Preparar datos para el prompt (sin emojis)
    text = ""
    for r in rests:
        nombre = get_restaurant_name(r)
        rating = get_restaurant_rating(r)
        dist = round(r.get('dist', 0))
        direccion = r.get('direccion') or r.get('Dirección') or 'N/A'
        
        text += f"\n--- {nombre} ---\n"
        text += f"Rating: {rating} | Distancia: {dist}m\n"
        text += f"Dirección: {direccion}\n"
        
        # Horarios
        horarios = r.get('horarios', [])
        if horarios and len(horarios) > 0:
            text += f"Horarios: {horarios[0]}\n"
        
        if r.get('abierto_ahora'):
            text += "Estado: Abierto ahora\n"
        
        # Tipos
        tipos = r.get('tipos', [])
        if tipos:
            tipos_filtrados = [t for t in tipos if t in ['restaurant', 'bar', 'cafe', 'bakery']]
            if tipos_filtrados:
                text += f"Tipo: {', '.join(tipos_filtrados)}\n"
        
        # Servicios
        servicios = r.get('servicios', {})
        servicios_list = []
        if servicios:
            if servicios.get('dine_in'): servicios_list.append("comer en sitio")
            if servicios.get('takeout'): servicios_list.append("para llevar")
            if servicios.get('delivery'): servicios_list.append("domicilio")
            if servicios.get('serves_breakfast'): servicios_list.append("desayuno")
            if servicios.get('serves_lunch'): servicios_list.append("almuerzo")
            if servicios.get('serves_dinner'): servicios_list.append("cena")
            if servicios.get('serves_vegetarian_food'): servicios_list.append("vegetariano")
        
        if servicios_list:
            text += f"Servicios: {', '.join(servicios_list)}\n"
        
        if r.get('pet_friendly'):
            text += "Pet Friendly: Si\n"
        
        # Editorial
        editorial = r.get('editorial_summary', {})
        if editorial and editorial.get('overview'):
            text += f"Descripción: {editorial['overview']}\n"
        
        # Reseña
        resenas = r.get('reseñas', [])
        if resenas and isinstance(resenas, list) and len(resenas) > 0:
            rating_resena = resenas[0].get('rating', 'N/A')
            texto_resena = resenas[0].get('texto', '')[:150]
            if texto_resena:
                text += f"Reseña ({rating_resena}/5): {texto_resena}...\n"
        
        # Delivery
        delivery = r.get('delivery', {})
        if delivery:
            apps = []
            if delivery.get('rappi'): apps.append("Rappi")
            if delivery.get('ubereats'): apps.append("Uber Eats")
            if apps:
                text += f"Apps delivery: {', '.join(apps)}\n"

    prompt = f"""
Analiza estos restaurantes de Bogotá y genera un resumen útil en español:

{text}

Estructura tu respuesta así:

**RESUMEN**
Descripción breve de la variedad disponible

**TOP 3 RECOMENDADOS**
1. [Nombre] - Por qué destacan y qué ofrecen
2. [Nombre] - Por qué destacan y qué ofrecen  
3. [Nombre] - Por qué destacan y qué ofrecen

**OPINIONES DESTACADAS**
Qué dicen los clientes (positivo y negativo)

**CONSEJOS**
- Mejor opción para [ocasión]
- Opciones especiales disponibles

Máximo 350 palabras, tono amigable.
"""

    try:
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        # Si falla OpenAI, mostrar resumen básico sin IA
        fallback = "## 📋 Restaurantes encontrados\n\n"
        fallback += "*No se pudo generar el resumen inteligente. Aquí está la lista de restaurantes:*\n\n"
        
        for idx, r in enumerate(rests[:5], 1):
            nombre = get_restaurant_name(r)
            rating = get_restaurant_rating(r)
            dist = round(r.get('dist', 0))
            
            fallback += f"**{idx}. {nombre}**\n"
            fallback += f"- ⭐ Rating: {rating}\n"
            fallback += f"- 📍 Distancia: {dist}m\n"
            
            resenas = r.get('reseñas', [])
            if resenas and isinstance(resenas, list) and len(resenas) > 0:
                texto = resenas[0].get('texto', '')[:100]
                if texto:
                    fallback += f"- 💬 \"{texto}...\"\n"
            fallback += "\n"
        
        fallback += f"\n*💡 Consejo: Verifica que tu API key de OpenAI tenga créditos disponibles en https://platform.openai.com/usage*"
        
        return fallback


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
            nearby = filter_nearby(user_lat, user_lng, df, max_m=10000)

        if len(nearby) == 0:
            st.warning("⚠️ No se encontraron restaurantes en un radio de 10km")
        else:
            st.info(f"📍 Se encontraron {len(nearby)} restaurantes en un radio de 10km")
            
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
            st.subheader("📋 Análisis y Recomendaciones")
            with st.spinner("Generando análisis inteligente..."):
                summary = summarize_restaurants(nearby.to_dict(orient="records"))
            
            # Mostrar el resumen en un contenedor limpio
            st.markdown(summary)

            # ---- TABLA ----
            st.subheader("📍 Detalle de Restaurantes")
            
            # Preparar datos para mostrar
            display_data = []
            for idx, row in nearby.iterrows():
                nombre = get_restaurant_name(row)
                rating = get_restaurant_rating(row)
                dist = round(row.get('dist', 0))
                direccion = row.get('direccion') or row.get('Dirección') or row.get('address') or 'N/A'
                
                # Horarios
                horarios = row.get('horarios', [])
                horario_txt = horarios[0] if horarios and len(horarios) > 0 else 'No disponible'
                
                # Estado
                estado = 'Abierto' if row.get('abierto_ahora') else 'Cerrado'
                
                display_data.append({
                    'Restaurante': nombre,
                    'Rating': rating,
                    'Distancia (m)': dist,
                    'Estado': estado,
                    'Dirección': direccion,
                    'Horarios': horario_txt
                })
            
            display_df = pd.DataFrame(display_data)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.error("❌ No se pudo encontrar la ubicación. Intenta con una dirección más específica.")
