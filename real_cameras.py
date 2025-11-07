"""
TAVIT Platform v4.0 - Sistema de Cámaras en Tiempo Real
Integración con feeds públicos de cámaras de tráfico, ciudad y seguridad
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import httpx
import asyncio
import json
import os
import re
from datetime import datetime
from io import BytesIO
import base64

router = APIRouter(prefix="/api/v1/cameras", tags=["Real-time Cameras"])

# Fuentes de cámaras públicas reales
CAMERA_SOURCES = {
    "traffic_nyc": {
        "name": "NYC Traffic Cameras",
        "base_url": "https://webcams.nyctmc.org/api/cameras/",
        "type": "traffic",
        "location": "New York, USA",
        "description": "Cámaras de tráfico en tiempo real de NYC"
    },
    "earthcam": {
        "name": "EarthCam Network", 
        "base_url": "https://www.earthcam.com/",
        "type": "city",
        "location": "Global",
        "description": "Red global de cámaras web en vivo"
    },
    "traffic_caltrans": {
        "name": "Caltrans Traffic",
        "base_url": "https://cwwp2.dot.ca.gov/",
        "type": "traffic", 
        "location": "California, USA",
        "description": "Cámaras de tráfico de California"
    },
    "weather_cams": {
        "name": "Weather Underground Webcams",
        "base_url": "https://www.wunderground.com/webcams",
        "type": "weather",
        "location": "Global",
        "description": "Cámaras meteorológicas globales"
    },
    "port_cameras": {
        "name": "Port Authority Cameras",
        "base_url": "https://www.panynj.gov/",
        "type": "port",
        "location": "NY/NJ Ports",
        "description": "Cámaras de puertos y aeropuertos"
    }
}

# Cámaras específicas de ejemplo con URLs reales
FEATURED_CAMERAS = [
    {
        "id": "nyc_times_square",
        "name": "Times Square Live",
        "location": "New York, NY",
        "url": "https://cdn-004.whatsupcams.com/hls/hr_14298_26896.m3u8",
        "thumbnail": "https://cdn-004.whatsupcams.com/snapshot/hr_14298_26896.jpg",
        "type": "city",
        "description": "Vista en vivo de Times Square 24/7"
    },
    {
        "id": "miami_beach", 
        "name": "Miami Beach Cam",
        "location": "Miami, FL",
        "url": "https://cam.miami-beach.net/",
        "thumbnail": "https://www.miamidade.gov/img/webcam1.jpg",
        "type": "beach",
        "description": "Playa de Miami en tiempo real"
    },
    {
        "id": "golden_gate",
        "name": "Golden Gate Bridge",
        "location": "San Francisco, CA", 
        "url": "https://www.goldengate.org/webcam/",
        "thumbnail": "https://www.goldengate.org/assets/1/6/WebCam1.jpg",
        "type": "landmark",
        "description": "Puente Golden Gate desde múltiples ángulos"
    },
    {
        "id": "las_vegas_strip",
        "name": "Las Vegas Strip",
        "location": "Las Vegas, NV",
        "url": "https://www.vegascam.com/",
        "thumbnail": "https://www.vegascam.com/current.jpg",
        "type": "city",
        "description": "Vista panorámica del Strip de Las Vegas"
    },
    {
        "id": "yellowstone",
        "name": "Yellowstone Old Faithful",
        "location": "Yellowstone, WY",
        "url": "https://www.nps.gov/yell/learn/photosmultimedia/webcams.htm",
        "thumbnail": "https://www.nps.gov/webcams-yell/oldfaithfulcam.jpg", 
        "type": "nature",
        "description": "Géiser Old Faithful en vivo"
    }
]

# Modelos Pydantic
class CameraSearchRequest(BaseModel):
    location: Optional[str] = Field(None, description="Ubicación geográfica")
    camera_type: Optional[str] = Field(None, description="Tipo: traffic, city, weather, port, nature")
    radius: Optional[int] = Field(50, description="Radio de búsqueda en km")
    limit: Optional[int] = Field(20, description="Límite de resultados")

class CameraStreamRequest(BaseModel):
    camera_id: str = Field(..., description="ID de la cámara")
    quality: Optional[str] = Field("standard", description="Calidad: low, standard, high")
    duration: Optional[int] = Field(300, description="Duración máxima en segundos")

# Cache para metadatos de cámaras
camera_cache = {}
cache_duration = 600  # 10 minutos

@router.get("/sources")
async def get_camera_sources():
    """
    Obtener fuentes de cámaras disponibles
    """
    try:
        return {
            "sources": CAMERA_SOURCES,
            "featured_cameras": FEATURED_CAMERAS,
            "total_sources": len(CAMERA_SOURCES),
            "total_featured": len(FEATURED_CAMERAS),
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo fuentes: {str(e)}")

@router.post("/search")
async def search_cameras(request: CameraSearchRequest):
    """
    Buscar cámaras por ubicación y tipo
    """
    try:
        results = []
        
        # Filtrar cámaras destacadas
        for camera in FEATURED_CAMERAS:
            include_camera = True
            
            # Filtro por ubicación
            if request.location and request.location.lower() not in camera["location"].lower():
                include_camera = False
            
            # Filtro por tipo
            if request.camera_type and camera["type"] != request.camera_type:
                include_camera = False
            
            if include_camera:
                results.append(camera)
        
        # Buscar en fuentes adicionales usando APIs públicas
        if request.location:
            additional_cameras = await search_public_cameras(request.location, request.camera_type)
            results.extend(additional_cameras[:request.limit - len(results)])
        
        return {
            "cameras": results[:request.limit],
            "total_found": len(results),
            "search_criteria": {
                "location": request.location,
                "type": request.camera_type,
                "radius": request.radius
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")

@router.get("/stream/{camera_id}")
async def get_camera_stream(camera_id: str, quality: str = "standard"):
    """
    Obtener URL de stream de cámara específica
    """
    try:
        # Buscar cámara en featured cameras
        camera = next((cam for cam in FEATURED_CAMERAS if cam["id"] == camera_id), None)
        
        if not camera:
            raise HTTPException(status_code=404, detail="Cámara no encontrada")
        
        # Verificar disponibilidad del stream
        stream_info = await verify_camera_stream(camera["url"])
        
        if not stream_info["available"]:
            raise HTTPException(status_code=503, detail="Stream no disponible temporalmente")
        
        # Registrar visualización en Supabase
        await log_camera_viewing(camera_id, quality)
        
        return {
            "camera_id": camera_id,
            "name": camera["name"],
            "location": camera["location"],
            "stream_url": camera["url"],
            "thumbnail": camera["thumbnail"],
            "quality": quality,
            "type": camera["type"],
            "description": camera["description"],
            "status": "active",
            "viewers": stream_info.get("viewers", 0),
            "uptime": stream_info.get("uptime", "unknown"),
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo stream: {str(e)}")

@router.get("/snapshot/{camera_id}")
async def get_camera_snapshot(camera_id: str):
    """
    Obtener snapshot actual de una cámara
    """
    try:
        camera = next((cam for cam in FEATURED_CAMERAS if cam["id"] == camera_id), None)
        
        if not camera:
            raise HTTPException(status_code=404, detail="Cámara no encontrada")
        
        # Obtener imagen actual
        async with httpx.AsyncClient(timeout=10.0) as client:
            if "thumbnail" in camera and camera["thumbnail"]:
                response = await client.get(camera["thumbnail"])
                
                if response.status_code == 200:
                    return StreamingResponse(
                        BytesIO(response.content),
                        media_type="image/jpeg",
                        headers={
                            "Cache-Control": "no-cache",
                            "X-Camera-ID": camera_id,
                            "X-Timestamp": datetime.utcnow().isoformat()
                        }
                    )
        
        # Imagen placeholder si no hay snapshot
        placeholder_image = create_placeholder_image(camera["name"], camera["location"])
        return StreamingResponse(
            BytesIO(placeholder_image),
            media_type="image/png"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo snapshot: {str(e)}")

@router.get("/nearby")
async def get_nearby_cameras(lat: float, lon: float, radius: int = 50, limit: int = 10):
    """
    Buscar cámaras cercanas por coordenadas GPS
    """
    try:
        # Coordenadas aproximadas de cámaras principales
        camera_coords = {
            "nyc_times_square": (40.7580, -73.9855),
            "miami_beach": (25.7617, -80.1918),
            "golden_gate": (37.8199, -122.4783),
            "las_vegas_strip": (36.1162, -115.1722),
            "yellowstone": (44.4605, -110.8281)
        }
        
        nearby_cameras = []
        
        for camera in FEATURED_CAMERAS:
            if camera["id"] in camera_coords:
                cam_lat, cam_lon = camera_coords[camera["id"]]
                distance = calculate_distance(lat, lon, cam_lat, cam_lon)
                
                if distance <= radius:
                    camera_info = camera.copy()
                    camera_info["distance_km"] = round(distance, 2)
                    camera_info["coordinates"] = {"lat": cam_lat, "lon": cam_lon}
                    nearby_cameras.append(camera_info)
        
        # Ordenar por distancia
        nearby_cameras.sort(key=lambda x: x["distance_km"])
        
        return {
            "cameras": nearby_cameras[:limit],
            "search_location": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "total_found": len(nearby_cameras)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando cámaras cercanas: {str(e)}")

@router.get("/status")
async def get_cameras_status():
    """
    Estado general del sistema de cámaras
    """
    try:
        active_cameras = 0
        offline_cameras = 0
        
        # Verificar estado de cámaras principales
        for camera in FEATURED_CAMERAS:
            status = await verify_camera_stream(camera["url"])
            if status["available"]:
                active_cameras += 1
            else:
                offline_cameras += 1
        
        return {
            "total_cameras": len(FEATURED_CAMERAS),
            "active_cameras": active_cameras,
            "offline_cameras": offline_cameras,
            "sources_available": len(CAMERA_SOURCES),
            "uptime_percentage": round((active_cameras / len(FEATURED_CAMERAS)) * 100, 1),
            "last_check": datetime.utcnow().isoformat(),
            "system_status": "operational" if active_cameras > 0 else "degraded"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verificando estado: {str(e)}")

# Funciones auxiliares

async def search_public_cameras(location: str, camera_type: Optional[str] = None) -> List[Dict]:
    """
    Buscar cámaras en APIs públicas
    """
    try:
        cameras = []
        
        # Buscar en base de datos de cámaras públicas (simulado)
        public_cameras = [
            {
                "id": f"pub_cam_{hash(location)}",
                "name": f"Cámara Pública {location}",
                "location": location,
                "url": f"https://example.com/stream/{location}",
                "thumbnail": f"https://example.com/thumb/{location}.jpg",
                "type": camera_type or "public",
                "description": f"Cámara pública en {location}"
            }
        ]
        
        return public_cameras
        
    except Exception as e:
        print(f"Error buscando cámaras públicas: {e}")
        return []

async def verify_camera_stream(url: str) -> Dict[str, Any]:
    """
    Verificar disponibilidad de stream de cámara
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(url)
            
            return {
                "available": response.status_code < 400,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0,
                "viewers": 0,  # Placeholder
                "uptime": "99.5%"  # Placeholder
            }
            
    except Exception:
        return {
            "available": False,
            "status_code": 0,
            "response_time": 0,
            "error": "Connection timeout"
        }

async def log_camera_viewing(camera_id: str, quality: str):
    """
    Registrar visualización de cámara en Supabase
    """
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            return
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{supabase_url}/rest/v1/camera_viewing_history",
                headers={
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "apikey": supabase_key
                },
                json={
                    "camera_source_id": camera_id,
                    "session_duration": 0,  # Se actualizará cuando termine la sesión
                    "viewed_at": datetime.utcnow().isoformat()
                }
            )
            
    except Exception as e:
        print(f"Error logging camera viewing: {e}")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcular distancia entre dos puntos GPS en km
    """
    from math import radians, cos, sin, asin, sqrt
    
    # Radio de la Tierra en km
    R = 6371
    
    # Convertir a radianes
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Fórmula de Haversine
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    return R * c

def create_placeholder_image(camera_name: str, location: str) -> bytes:
    """
    Crear imagen placeholder para cámaras offline
    """
    try:
        # Crear una imagen placeholder simple en formato texto
        placeholder_text = f"Camera: {camera_name}\nLocation: {location}\nTemporarily unavailable"
        return placeholder_text.encode('utf-8')
        
    except Exception as e:
        # Imagen mínima si hay error
        return b"Camera placeholder image not available"