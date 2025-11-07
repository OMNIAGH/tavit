"""
TAVIT Platform v3.1 - Monitoreo de APIs en Tiempo Real
Sistema de estado de APIs con LEDs y métricas operativas
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
import httpx
import asyncio
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/v1", tags=["API Status Monitor"])

# Configuración de APIs a monitorear
APIS_CONFIG = {
    "serpapi": {
        "name": "SerpAPI",
        "description": "Búsquedas web y redes sociales", 
        "url": "https://serpapi.com/search.json",
        "method": "GET",
        "params": {"engine": "google", "q": "test", "api_key": os.getenv("SERPAPI_KEY")},
        "headers": {},
        "timeout": 10,
        "expected_status": 200,
        "category": "osint"
    },
    "courtlistener": {
        "name": "CourtListener",
        "description": "Casos legales y jurisprudencia",
        "url": "https://www.courtlistener.com/api/rest/v3/search/",
        "method": "GET", 
        "params": {"q": "test", "format": "json"},
        "headers": {
            "Authorization": f"Token {os.getenv('COURTLISTENER_TOKEN')}",
            "User-Agent": os.getenv("COURTLISTENER_UA", "Tavix/1.0 (ceo@tavit.com)")
        },
        "timeout": 15,
        "expected_status": 200,
        "category": "legal"
    },
    "openai": {
        "name": "OpenAI GPT-4",
        "description": "Análisis de inteligencia artificial",
        "url": "https://api.openai.com/v1/models",
        "method": "GET",
        "params": {},
        "headers": {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        },
        "timeout": 10,
        "expected_status": 200,
        "category": "ai"
    },
    "catboost_fraud": {
        "name": "CatBoost Fraude",
        "description": "Modelo de detección de fraude",
        "url": "internal",
        "method": "INTERNAL",
        "category": "ml"
    },
    "catboost_risk": {
        "name": "CatBoost Riesgo", 
        "description": "Modelo de scoring de riesgo",
        "url": "internal",
        "method": "INTERNAL",
        "category": "ml"
    },
    "twitter_api": {
        "name": "Twitter/X API",
        "description": "Monitoreo redes sociales",
        "url": "https://api.twitter.com/2/users/by/username/twitter",
        "method": "GET",
        "params": {},
        "headers": {
            "Authorization": f"Bearer {os.getenv('TWITTER_BEARER_TOKEN', '')}"
        },
        "timeout": 10,
        "expected_status": 200,
        "category": "social"
    },
    "github_api": {
        "name": "GitHub API",
        "description": "Perfiles y repositorios",
        "url": "https://api.github.com/user",
        "method": "GET",
        "params": {},
        "headers": {
            "Authorization": f"token {os.getenv('GITHUB_TOKEN', '')}",
            "User-Agent": "TAVIT-Platform/1.0"
        },
        "timeout": 10,
        "expected_status": 200,
        "category": "osint"
    },
    "reddit_api": {
        "name": "Reddit API",
        "description": "Foros y discusiones",
        "url": "https://www.reddit.com/api/v1/me",
        "method": "GET",
        "params": {},
        "headers": {
            "Authorization": f"Bearer {os.getenv('REDDIT_ACCESS_TOKEN', '')}",
            "User-Agent": "TAVIT-Platform/1.0 by tavit"
        },
        "timeout": 10,
        "expected_status": 200,
        "category": "social"
    },
    "vinelink": {
        "name": "VINELink",
        "description": "Notificaciones prisión",
        "url": "https://www.vinelink.com/vinelink/servlet",
        "method": "GET",
        "params": {},
        "headers": {"User-Agent": "TAVIX-Platform/1.0"},
        "timeout": 15,
        "expected_status": 200,
        "category": "legal"
    },
    "pacer": {
        "name": "PACER",
        "description": "Casos federales",
        "url": "https://pcl.uscourts.gov/search",
        "method": "GET",
        "params": {},
        "headers": {"User-Agent": "TAVIX-Platform/1.0"},
        "timeout": 15,
        "expected_status": 200,
        "category": "legal"
    }
}

# Cache de estado de APIs
api_status_cache = {}
last_check_time = 0

async def check_api_status(api_name: str, config: Dict) -> Dict:
    """Verifica el estado de una API específica"""
    start_time = time.time()
    
    try:
        # APIs internas (CatBoost)
        if config["method"] == "INTERNAL":
            if "fraud" in api_name:
                from model_utils import ml_models
                status = "active" if hasattr(ml_models, 'fraud_model') else "inactive"
            elif "risk" in api_name:
                from model_utils import ml_models  
                status = "active" if hasattr(ml_models, 'risk_model') else "inactive"
            else:
                status = "active"
                
            return {
                "name": config["name"],
                "description": config["description"],
                "status": status,
                "response_time": round((time.time() - start_time) * 1000, 2),
                "last_check": datetime.now().isoformat(),
                "category": config["category"],
                "error": None
            }
        
        # APIs externas
        async with httpx.AsyncClient(timeout=httpx.Timeout(config["timeout"])) as client:
            if config["method"] == "GET":
                response = await client.get(
                    config["url"],
                    params=config["params"],
                    headers=config["headers"]
                )
            elif config["method"] == "POST":
                response = await client.post(
                    config["url"],
                    json=config.get("data", {}),
                    headers=config["headers"]
                )
            else:
                raise ValueError(f"Método HTTP no soportado: {config['method']}")
        
        response_time = round((time.time() - start_time) * 1000, 2)
        
        # Determinar estado basado en código de respuesta
        if response.status_code == config["expected_status"]:
            status = "active"
        elif response.status_code in [429, 503, 504]:
            status = "maintenance" 
        else:
            status = "inactive"
            
        return {
            "name": config["name"],
            "description": config["description"], 
            "status": status,
            "status_code": response.status_code,
            "response_time": response_time,
            "last_check": datetime.now().isoformat(),
            "category": config["category"],
            "error": None
        }
        
    except httpx.TimeoutException:
        return {
            "name": config["name"],
            "description": config["description"],
            "status": "inactive",
            "response_time": round((time.time() - start_time) * 1000, 2),
            "last_check": datetime.now().isoformat(),
            "category": config["category"],
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "name": config["name"],
            "description": config["description"],
            "status": "inactive", 
            "response_time": round((time.time() - start_time) * 1000, 2),
            "last_check": datetime.now().isoformat(),
            "category": config["category"],
            "error": str(e)[:100]
        }

async def check_all_apis() -> Dict:
    """Verifica el estado de todas las APIs en paralelo"""
    global api_status_cache, last_check_time
    
    # Cache por 30 segundos para evitar spam
    current_time = time.time()
    if current_time - last_check_time < 30 and api_status_cache:
        return api_status_cache
    
    # Verificar todas las APIs en paralelo
    tasks = [
        check_api_status(api_name, config) 
        for api_name, config in APIS_CONFIG.items()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Procesar resultados
    apis_status = {}
    categories_summary = {"osint": 0, "legal": 0, "ai": 0, "ml": 0, "social": 0}
    overall_health = {"active": 0, "maintenance": 0, "inactive": 0}
    
    for result in results:
        if isinstance(result, Exception):
            continue
            
        api_name = result["name"].lower().replace(" ", "_").replace("/", "_")
        apis_status[api_name] = result
        
        # Contar por categoría
        category = result["category"]
        if category in categories_summary:
            categories_summary[category] += 1
            
        # Contar por estado
        status = result["status"]
        if status in overall_health:
            overall_health[status] += 1
    
    # Calcular métricas generales
    total_apis = len(results)
    health_percentage = round((overall_health["active"] / total_apis) * 100, 1) if total_apis > 0 else 0
    
    api_status_cache = {
        "apis": apis_status,
        "summary": {
            "total_apis": total_apis,
            "health_percentage": health_percentage,
            "categories": categories_summary,
            "status_breakdown": overall_health
        },
        "last_updated": datetime.now().isoformat()
    }
    
    last_check_time = current_time
    return api_status_cache

@router.get("/api-status")
async def get_api_status():
    """
    Obtiene el estado en tiempo real de todas las APIs
    
    Returns:
        Dict: Estado de todas las APIs con métricas y LEDs de estado
    """
    try:
        status_data = await check_all_apis()
        return JSONResponse(content=status_data)
        
    except Exception as e:
        return JSONResponse(
            content={
                "error": f"Error al verificar APIs: {str(e)}",
                "apis": {},
                "summary": {
                    "total_apis": 0,
                    "health_percentage": 0,
                    "categories": {},
                    "status_breakdown": {"active": 0, "maintenance": 0, "inactive": 0}
                }
            },
            status_code=500
        )

@router.get("/api-status/{api_name}")
async def get_specific_api_status(api_name: str):
    """
    Obtiene el estado de una API específica
    
    Args:
        api_name: Nombre de la API a verificar
        
    Returns:
        Dict: Estado detallado de la API específica
    """
    try:
        if api_name not in APIS_CONFIG:
            return JSONResponse(
                content={"error": f"API '{api_name}' no encontrada"},
                status_code=404
            )
        
        config = APIS_CONFIG[api_name]
        status = await check_api_status(api_name, config)
        
        return JSONResponse(content=status)
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error al verificar API {api_name}: {str(e)}"},
            status_code=500
        )

@router.post("/api-status/refresh")
async def refresh_api_status():
    """
    Fuerza una actualización del estado de todas las APIs
    """
    try:
        global api_status_cache, last_check_time
        
        # Limpiar cache para forzar actualización
        api_status_cache = {}
        last_check_time = 0
        
        status_data = await check_all_apis()
        
        return JSONResponse(content={
            "message": "Estado de APIs actualizado exitosamente",
            "data": status_data
        })
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error al actualizar APIs: {str(e)}"},
            status_code=500
        )

@router.get("/api-status/health-summary")
async def get_health_summary():
    """
    Obtiene un resumen simplificado del estado de salud del sistema
    
    Returns:
        Dict: Resumen con porcentajes y conteos por categoría
    """
    try:
        status_data = await check_all_apis()
        
        return JSONResponse(content={
            "overall_health": status_data["summary"]["health_percentage"],
            "total_apis": status_data["summary"]["total_apis"],
            "active_count": status_data["summary"]["status_breakdown"]["active"],
            "categories": status_data["summary"]["categories"],
            "last_updated": status_data["last_updated"]
        })
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error al obtener resumen: {str(e)}"},
            status_code=500
        )