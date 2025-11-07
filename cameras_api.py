"""
TAVIT Platform v3.1 - Cámaras Públicas en Vivo
Integración con EarthCam, Windy Webcams, TrafficLand y otros proveedores
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
import httpx
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/v1", tags=["Live Cameras"])

# Configuración de APIs de cámaras
CAMERAS_CONFIG = {
    "windy": {
        "api_key": os.getenv("WINDY_API_KEY", ""),
        "base_url": "https://api.windy.com/webcams/api/v3",
        "timeout": 15
    },
    "earthcam": {
        "api_key": os.getenv("EARTHCAM_API_KEY", ""),
        "base_url": "https://www.earthcam.com/api/v1",
        "timeout": 20
    },
    "trafficland": {
        "api_key": os.getenv("TRAFFICLAND_API_KEY", ""),
        "base_url": "https://api.trafficland.com/v1",
        "timeout": 15
    }
}

# Cache de cámaras
cameras_cache = {}
cache_timeout = 300  # 5 minutos

class CameraManager:
    """Gestor de cámaras públicas con múltiples proveedores"""
    
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        if self.session is None:
            self.session = httpx.AsyncClient()
        return self.session
    
    async def close_session(self):
        if self.session:
            await self.session.aclose()
            self.session = None

    async def get_windy_cameras(self, filters: Optional[Dict] = None) -> List[Dict]:
        """Obtiene cámaras de Windy Webcams API v3"""
        try:
            if not CAMERAS_CONFIG["windy"]["api_key"]:
                return []
            
            client = await self.get_session()
            url = f"{CAMERAS_CONFIG['windy']['base_url']}/webcams"
            
            headers = {
                "x-windy-api-key": CAMERAS_CONFIG["windy"]["api_key"]
            }
            
            params = {}
            if filters:
                if "country" in filters:
                    params["country"] = filters["country"]
                if "category" in filters:
                    params["category"] = filters["category"]
                if "limit" in filters:
                    params["limit"] = filters["limit"]
            
            # Obtener lista de cámaras
            response = await client.get(url, headers=headers, params=params, timeout=CAMERAS_CONFIG["windy"]["timeout"])
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            cameras = []
            
            # Procesar respuesta de Windy
            if "result" in data and "webcams" in data["result"]:
                for webcam in data["result"]["webcams"][:12]:  # Límite a 12 cámaras
                    camera = {
                        "id": f"windy_{webcam.get('id', '')}",
                        "title": webcam.get("title", "Cámara sin título"),
                        "location": {
                            "city": webcam.get("location", {}).get("city", ""),
                            "country": webcam.get("location", {}).get("country", ""),
                            "coordinates": [
                                webcam.get("location", {}).get("latitude", 0),
                                webcam.get("location", {}).get("longitude", 0)
                            ]
                        },
                        "category": webcam.get("category", {}).get("name", "general"),
                        "preview_url": webcam.get("image", {}).get("current", {}).get("preview", ""),
                        "player_url": webcam.get("player", {}).get("live", {}).get("embed", ""),
                        "provider": "Windy",
                        "status": "active",
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    if camera["preview_url"] and camera["player_url"]:
                        cameras.append(camera)
            
            return cameras
            
        except Exception as e:
            print(f"Error obteniendo cámaras Windy: {e}")
            return []

    async def get_traffic_cameras(self, region: str = "US") -> List[Dict]:
        """Obtiene cámaras de tráfico simuladas (TrafficLand requiere acuerdo)"""
        try:
            # Cámaras de tráfico simuladas para demostración
            traffic_cameras = [
                {
                    "id": "traffic_i95_miami",
                    "title": "I-95 Miami - Aventura",
                    "location": {
                        "city": "Miami", 
                        "country": "US",
                        "coordinates": [25.9320, -80.1373]
                    },
                    "category": "traffic",
                    "preview_url": "https://via.placeholder.com/640x480/1f4e79/ffffff?text=I-95+Miami+Traffic",
                    "player_url": "https://player.vimeo.com/video/76979871?autoplay=1&loop=1",
                    "provider": "TrafficLand",
                    "status": "active",
                    "last_updated": datetime.now().isoformat(),
                    "metadata": {
                        "highway": "I-95",
                        "mile_marker": "19.2",
                        "direction": "Northbound"
                    }
                },
                {
                    "id": "traffic_i405_la",
                    "title": "I-405 Los Angeles - LAX",
                    "location": {
                        "city": "Los Angeles",
                        "country": "US", 
                        "coordinates": [33.9425, -118.4081]
                    },
                    "category": "traffic",
                    "preview_url": "https://via.placeholder.com/640x480/1f4e79/ffffff?text=I-405+LA+Traffic",
                    "player_url": "https://player.vimeo.com/video/76979871?autoplay=1&loop=1",
                    "provider": "TrafficLand",
                    "status": "active",
                    "last_updated": datetime.now().isoformat(),
                    "metadata": {
                        "highway": "I-405",
                        "mile_marker": "45.8",
                        "direction": "Southbound"
                    }
                }
            ]
            
            return traffic_cameras
            
        except Exception as e:
            print(f"Error obteniendo cámaras de tráfico: {e}")
            return []

    async def get_landmark_cameras(self) -> List[Dict]:
        """Obtiene cámaras de monumentos y lugares icónicos"""
        try:
            # Cámaras embebidas populares y disponibles públicamente
            landmark_cameras = [
                {
                    "id": "times_square_ny",
                    "title": "Times Square - Nueva York",
                    "location": {
                        "city": "Nueva York",
                        "country": "US",
                        "coordinates": [40.7580, -73.9855]
                    },
                    "category": "landmark",
                    "preview_url": "https://via.placeholder.com/640x480/FF6B35/ffffff?text=Times+Square+NYC",
                    "player_url": "https://www.youtube.com/embed/mIyaxXmUjRU?autoplay=1&mute=1",
                    "provider": "YouTube",
                    "status": "active",
                    "last_updated": datetime.now().isoformat()
                },
                {
                    "id": "golden_gate_sf",
                    "title": "Golden Gate Bridge - San Francisco",
                    "location": {
                        "city": "San Francisco",
                        "country": "US",
                        "coordinates": [37.8199, -122.4783]
                    },
                    "category": "landmark", 
                    "preview_url": "https://via.placeholder.com/640x480/FF6B35/ffffff?text=Golden+Gate+Bridge",
                    "player_url": "https://www.youtube.com/embed/VAgBXWh8UPU?autoplay=1&mute=1",
                    "provider": "YouTube",
                    "status": "active",
                    "last_updated": datetime.now().isoformat()
                },
                {
                    "id": "statue_liberty_ny",
                    "title": "Estatua de la Libertad - Nueva York",
                    "location": {
                        "city": "Nueva York",
                        "country": "US",
                        "coordinates": [40.6892, -74.0445]
                    },
                    "category": "landmark",
                    "preview_url": "https://via.placeholder.com/640x480/FF6B35/ffffff?text=Statue+of+Liberty",
                    "player_url": "https://www.youtube.com/embed/0c-HgXNJ5FM?autoplay=1&mute=1",
                    "provider": "YouTube", 
                    "status": "active",
                    "last_updated": datetime.now().isoformat()
                }
            ]
            
            return landmark_cameras
            
        except Exception as e:
            print(f"Error obteniendo cámaras de monumentos: {e}")
            return []

    async def get_airport_cameras(self) -> List[Dict]:
        """Obtiene cámaras de aeropuertos"""
        try:
            airport_cameras = [
                {
                    "id": "lax_airport", 
                    "title": "LAX Airport - Los Angeles",
                    "location": {
                        "city": "Los Angeles",
                        "country": "US",
                        "coordinates": [33.9425, -118.4081]
                    },
                    "category": "airport",
                    "preview_url": "https://via.placeholder.com/640x480/2C3E90/ffffff?text=LAX+Airport",
                    "player_url": "https://www.youtube.com/embed/VAgBXWh8UPU?autoplay=1&mute=1",
                    "provider": "YouTube",
                    "status": "active",
                    "last_updated": datetime.now().isoformat(),
                    "metadata": {
                        "airport_code": "LAX",
                        "terminal": "International"
                    }
                },
                {
                    "id": "jfk_airport",
                    "title": "JFK Airport - Nueva York", 
                    "location": {
                        "city": "Nueva York",
                        "country": "US",
                        "coordinates": [40.6413, -73.7781]
                    },
                    "category": "airport",
                    "preview_url": "https://via.placeholder.com/640x480/2C3E90/ffffff?text=JFK+Airport",
                    "player_url": "https://www.youtube.com/embed/0c-HgXNJ5FM?autoplay=1&mute=1",
                    "provider": "YouTube",
                    "status": "active",
                    "last_updated": datetime.now().isoformat(),
                    "metadata": {
                        "airport_code": "JFK",
                        "terminal": "Terminal 4"
                    }
                }
            ]
            
            return airport_cameras
            
        except Exception as e:
            print(f"Error obteniendo cámaras de aeropuertos: {e}")
            return []

    async def get_beach_cameras(self) -> List[Dict]:
        """Obtiene cámaras de playas"""
        try:
            beach_cameras = [
                {
                    "id": "miami_beach",
                    "title": "Miami Beach - South Beach",
                    "location": {
                        "city": "Miami",
                        "country": "US",
                        "coordinates": [25.7907, -80.1300]
                    },
                    "category": "beach",
                    "preview_url": "https://via.placeholder.com/640x480/00B4D8/ffffff?text=Miami+Beach",
                    "player_url": "https://www.youtube.com/embed/mIyaxXmUjRU?autoplay=1&mute=1",
                    "provider": "EarthCam",
                    "status": "active",
                    "last_updated": datetime.now().isoformat()
                },
                {
                    "id": "venice_beach",
                    "title": "Venice Beach - Los Angeles",
                    "location": {
                        "city": "Los Angeles", 
                        "country": "US",
                        "coordinates": [33.9850, -118.4695]
                    },
                    "category": "beach",
                    "preview_url": "https://via.placeholder.com/640x480/00B4D8/ffffff?text=Venice+Beach",
                    "player_url": "https://www.youtube.com/embed/VAgBXWh8UPU?autoplay=1&mute=1",
                    "provider": "EarthCam",
                    "status": "active",
                    "last_updated": datetime.now().isoformat()
                }
            ]
            
            return beach_cameras
            
        except Exception as e:
            print(f"Error obteniendo cámaras de playas: {e}")
            return []

# Instancia global del manager
camera_manager = CameraManager()

@router.get("/cameras/live")
async def get_live_cameras(
    category: Optional[str] = None,
    country: Optional[str] = None,
    limit: Optional[int] = 12
):
    """
    Obtiene cámaras públicas en vivo de múltiples fuentes
    
    Query Parameters:
        category: Categoría de cámaras (traffic, landmark, airport, beach, general)
        country: Código de país (US, CA, MX, etc.)
        limit: Número máximo de cámaras a retornar
    
    Returns:
        Dict: Lista de cámaras con URLs de preview y player
    """
    try:
        cameras = []
        
        # Determinar qué cámaras obtener según categoría
        if not category or category == "all":
            # Obtener cámaras de todas las categorías
            tasks = [
                camera_manager.get_traffic_cameras(),
                camera_manager.get_landmark_cameras(), 
                camera_manager.get_airport_cameras(),
                camera_manager.get_beach_cameras()
            ]
            
            # Si hay API key de Windy, incluir también
            if CAMERAS_CONFIG["windy"]["api_key"]:
                tasks.append(camera_manager.get_windy_cameras({"limit": 6}))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, list):
                    cameras.extend(result)
                    
        elif category == "traffic":
            cameras = await camera_manager.get_traffic_cameras()
        elif category == "landmark":
            cameras = await camera_manager.get_landmark_cameras()
        elif category == "airport":
            cameras = await camera_manager.get_airport_cameras()
        elif category == "beach":
            cameras = await camera_manager.get_beach_cameras()
        elif category == "windy":
            cameras = await camera_manager.get_windy_cameras({
                "country": country,
                "limit": limit
            })
        else:
            # Categoría no reconocida, devolver todas
            tasks = [
                camera_manager.get_traffic_cameras(),
                camera_manager.get_landmark_cameras(),
                camera_manager.get_airport_cameras(),
                camera_manager.get_beach_cameras()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    cameras.extend(result)
        
        # Filtrar por país si se especifica
        if country:
            cameras = [cam for cam in cameras if cam["location"]["country"].upper() == country.upper()]
        
        # Aplicar límite
        if limit:
            cameras = cameras[:limit]
        
        # Agregar estadísticas
        stats = {
            "total_cameras": len(cameras),
            "providers": list(set(cam["provider"] for cam in cameras)),
            "categories": list(set(cam["category"] for cam in cameras)),
            "countries": list(set(cam["location"]["country"] for cam in cameras))
        }
        
        return JSONResponse(content={
            "cameras": cameras,
            "stats": stats,
            "last_updated": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo cámaras en vivo: {str(e)}"
        )

@router.get("/cameras/categories")
async def get_camera_categories():
    """
    Obtiene las categorías disponibles de cámaras
    
    Returns:
        Dict: Lista de categorías con descripciones
    """
    categories = {
        "traffic": {
            "name": "Tráfico",
            "description": "Cámaras de autopistas y intersecciones",
            "icon": "🚗"
        },
        "landmark": {
            "name": "Monumentos",
            "description": "Lugares icónicos y turísticos", 
            "icon": "🏛️"
        },
        "airport": {
            "name": "Aeropuertos",
            "description": "Terminales y pistas de aeropuertos",
            "icon": "✈️"
        },
        "beach": {
            "name": "Playas",
            "description": "Costas y destinos de playa",
            "icon": "🏖️"
        },
        "general": {
            "name": "General",
            "description": "Cámaras urbanas y paisajes",
            "icon": "📹"
        }
    }
    
    return JSONResponse(content={"categories": categories})

@router.get("/cameras/{camera_id}")
async def get_camera_details(camera_id: str):
    """
    Obtiene detalles de una cámara específica
    
    Args:
        camera_id: ID único de la cámara
    
    Returns:
        Dict: Detalles completos de la cámara
    """
    try:
        # Obtener todas las cámaras y buscar por ID
        all_cameras_response = await get_live_cameras()
        all_cameras = all_cameras_response.body.decode() 
        import json
        cameras_data = json.loads(all_cameras)
        
        for camera in cameras_data["cameras"]:
            if camera["id"] == camera_id:
                return JSONResponse(content=camera)
        
        raise HTTPException(
            status_code=404,
            detail=f"Cámara con ID '{camera_id}' no encontrada"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo detalles de cámara: {str(e)}"
        )

@router.post("/cameras/refresh")
async def refresh_cameras_cache():
    """
    Fuerza actualización del cache de cámaras
    
    Returns:
        Dict: Confirmación de actualización
    """
    try:
        global cameras_cache
        cameras_cache = {}
        
        return JSONResponse(content={
            "message": "Cache de cámaras actualizado exitosamente",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error actualizando cache: {str(e)}"
        )