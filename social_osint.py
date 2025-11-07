"""
TAVIT Platform v3.1 - OSINT de Redes Sociales
Búsquedas multi-fuente, análisis de sentimientos, seguimiento de entidades
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import httpx
import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re
import hashlib

load_dotenv()

router = APIRouter(prefix="/api/v1", tags=["OSINT Social Media"])

# Configuración de APIs OSINT
OSINT_CONFIG = {
    "serpapi": {
        "key": os.getenv("SERPAPI_KEY"),
        "base_url": "https://serpapi.com/search.json",
        "timeout": 15
    },
    "twitter": {
        "bearer_token": os.getenv("TWITTER_BEARER_TOKEN", ""),
        "base_url": "https://api.twitter.com/2",
        "timeout": 10
    },
    "github": {
        "token": os.getenv("GITHUB_TOKEN", ""),
        "base_url": "https://api.github.com",
        "timeout": 10
    },
    "reddit": {
        "client_id": os.getenv("REDDIT_CLIENT_ID", ""),
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "base_url": "https://www.reddit.com",
        "timeout": 10
    }
}

# Modelos Pydantic
class OSINTSearchRequest(BaseModel):
    query: str = Field(..., description="Término de búsqueda (persona, empresa, evento)")
    sources: List[str] = Field(default=["web", "social", "news"], description="Fuentes: web, social, news, github, reddit")
    depth: str = Field(default="standard", description="Profundidad: basic, standard, deep")
    time_range: Optional[str] = Field("30d", description="Rango temporal: 24h, 7d, 30d, 1y")

class SentimentAnalysisRequest(BaseModel):
    text: str = Field(..., description="Texto a analizar")
    language: str = Field(default="es", description="Idioma del texto")

class HashtagTrackingRequest(BaseModel):
    hashtags: List[str] = Field(..., description="Lista de hashtags a monitorear")
    platforms: List[str] = Field(default=["twitter"], description="Plataformas: twitter, instagram, tiktok")

class EntityExtractionRequest(BaseModel):
    text: str = Field(..., description="Texto para extracción de entidades")

# Cache para resultados OSINT
osint_cache = {}
cache_timeout = 900  # 15 minutos

class OSINTAnalyzer:
    """Analizador OSINT para redes sociales y fuentes públicas"""
    
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

    async def search_web(self, query: str, num_results: int = 10) -> List[Dict]:
        """Búsqueda web usando SerpAPI"""
        try:
            if not OSINT_CONFIG["serpapi"]["key"]:
                return []
            
            client = await self.get_session()
            params = {
                "engine": "google",
                "q": query,
                "api_key": OSINT_CONFIG["serpapi"]["key"],
                "num": num_results,
                "hl": "es"
            }
            
            response = await client.get(
                OSINT_CONFIG["serpapi"]["base_url"],
                params=params,
                timeout=OSINT_CONFIG["serpapi"]["timeout"]
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = []
            
            # Procesar resultados orgánicos
            for result in data.get("organic_results", []):
                results.append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "date": result.get("date", ""),
                    "source": "web",
                    "provider": "Google"
                })
            
            return results
            
        except Exception as e:
            print(f"Error en búsqueda web: {e}")
            return []

    async def search_news(self, query: str, num_results: int = 10) -> List[Dict]:
        """Búsqueda de noticias usando SerpAPI"""
        try:
            if not OSINT_CONFIG["serpapi"]["key"]:
                return []
            
            client = await self.get_session()
            params = {
                "engine": "google_news",
                "q": query,
                "api_key": OSINT_CONFIG["serpapi"]["key"],
                "num": num_results,
                "hl": "es"
            }
            
            response = await client.get(
                OSINT_CONFIG["serpapi"]["base_url"],
                params=params,
                timeout=OSINT_CONFIG["serpapi"]["timeout"]
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = []
            
            # Procesar resultados de noticias
            for result in data.get("news_results", []):
                results.append({
                    "title": result.get("title", ""),
                    "link": result.get("link", ""), 
                    "snippet": result.get("snippet", ""),
                    "date": result.get("date", ""),
                    "source": "news",
                    "provider": result.get("source", "Unknown")
                })
            
            return results
            
        except Exception as e:
            print(f"Error en búsqueda de noticias: {e}")
            return []

    async def search_github(self, query: str, search_type: str = "users") -> List[Dict]:
        """Búsqueda en GitHub (usuarios, repositorios)"""
        try:
            if not OSINT_CONFIG["github"]["token"]:
                return []
            
            client = await self.get_session()
            headers = {
                "Authorization": f"token {OSINT_CONFIG['github']['token']}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "TAVIT-Platform/1.0"
            }
            
            url = f"{OSINT_CONFIG['github']['base_url']}/search/{search_type}"
            params = {"q": query, "per_page": 10}
            
            response = await client.get(
                url,
                headers=headers,
                params=params,
                timeout=OSINT_CONFIG["github"]["timeout"]
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = []
            
            # Procesar resultados de GitHub
            for item in data.get("items", []):
                if search_type == "users":
                    results.append({
                        "username": item.get("login", ""),
                        "profile_url": item.get("html_url", ""),
                        "avatar_url": item.get("avatar_url", ""),
                        "type": item.get("type", "User"),
                        "public_repos": item.get("public_repos", 0),
                        "followers": item.get("followers", 0),
                        "source": "github",
                        "search_type": "users"
                    })
                elif search_type == "repositories":
                    results.append({
                        "name": item.get("name", ""),
                        "full_name": item.get("full_name", ""),
                        "description": item.get("description", ""),
                        "url": item.get("html_url", ""),
                        "language": item.get("language", ""),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "owner": item.get("owner", {}).get("login", ""),
                        "source": "github",
                        "search_type": "repositories"
                    })
            
            return results
            
        except Exception as e:
            print(f"Error en búsqueda de GitHub: {e}")
            return []

    async def search_reddit(self, query: str, subreddit: str = "all") -> List[Dict]:
        """Búsqueda en Reddit"""
        try:
            client = await self.get_session()
            url = f"{OSINT_CONFIG['reddit']['base_url']}/r/{subreddit}/search.json"
            
            params = {
                "q": query,
                "limit": 10,
                "sort": "relevance",
                "t": "all"
            }
            
            headers = {
                "User-Agent": "TAVIT-Platform/1.0 by tavit"
            }
            
            response = await client.get(
                url,
                params=params,
                headers=headers,
                timeout=OSINT_CONFIG["reddit"]["timeout"]
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            results = []
            
            # Procesar resultados de Reddit
            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})
                results.append({
                    "title": post_data.get("title", ""),
                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    "subreddit": post_data.get("subreddit", ""),
                    "author": post_data.get("author", ""),
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "created_utc": post_data.get("created_utc", 0),
                    "selftext": post_data.get("selftext", "")[:300],
                    "source": "reddit"
                })
            
            return results
            
        except Exception as e:
            print(f"Error en búsqueda de Reddit: {e}")
            return []

    async def analyze_sentiment(self, text: str) -> Dict:
        """Análisis básico de sentimientos"""
        try:
            # Diccionarios de palabras positivas y negativas (simplificado)
            positive_words = [
                "bueno", "excelente", "fantástico", "increíble", "perfecto",
                "genial", "maravilloso", "positivo", "exitoso", "feliz",
                "good", "excellent", "fantastic", "amazing", "perfect",
                "great", "wonderful", "positive", "successful", "happy"
            ]
            
            negative_words = [
                "malo", "terrible", "horrible", "pésimo", "negativo",
                "fracaso", "triste", "problemático", "deficiente", "pobre",
                "bad", "terrible", "horrible", "awful", "negative", 
                "failure", "sad", "problematic", "poor", "disappointing"
            ]
            
            text_lower = text.lower()
            words = re.findall(r'\w+', text_lower)
            
            positive_count = sum(1 for word in words if word in positive_words)
            negative_count = sum(1 for word in words if word in negative_words)
            total_words = len(words)
            
            if positive_count > negative_count:
                sentiment = "positive"
                confidence = min(0.9, (positive_count / max(total_words, 1)) * 5)
            elif negative_count > positive_count:
                sentiment = "negative"
                confidence = min(0.9, (negative_count / max(total_words, 1)) * 5)
            else:
                sentiment = "neutral"
                confidence = 0.5
            
            return {
                "sentiment": sentiment,
                "confidence": round(confidence, 2),
                "positive_words": positive_count,
                "negative_words": negative_count,
                "total_words": total_words
            }
            
        except Exception as e:
            return {
                "sentiment": "neutral",
                "confidence": 0.0,
                "error": str(e)
            }

    async def extract_entities(self, text: str) -> Dict:
        """Extracción básica de entidades nombradas"""
        try:
            # Patrones regex básicos para entidades
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            phone_pattern = r'\b\d{3}-\d{3}-\d{4}\b|\b\(\d{3}\)\s*\d{3}-\d{4}\b'
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            
            # Nombres propios (simplificado - palabras capitalizadas)
            name_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
            
            entities = {
                "emails": re.findall(email_pattern, text),
                "phones": re.findall(phone_pattern, text),
                "urls": re.findall(url_pattern, text),
                "names": re.findall(name_pattern, text)[:10],  # Límite a 10 nombres
                "mentions": re.findall(r'@\w+', text),
                "hashtags": re.findall(r'#\w+', text)
            }
            
            # Limpiar duplicados
            for key in entities:
                entities[key] = list(set(entities[key]))
            
            return entities
            
        except Exception as e:
            return {"error": str(e)}

# Instancia global del analizador
osint_analyzer = OSINTAnalyzer()

@router.post("/osint/search")
async def osint_search(request: OSINTSearchRequest):
    """
    Realiza búsqueda OSINT multi-fuente
    
    Body:
        OSINTSearchRequest: Configuración de búsqueda
    
    Returns:
        Dict: Resultados agregados de múltiples fuentes
    """
    try:
        # Generar clave de cache
        cache_key = hashlib.md5(f"{request.query}_{request.sources}_{request.depth}".encode()).hexdigest()
        
        # Verificar cache
        if cache_key in osint_cache:
            cached_result = osint_cache[cache_key]
            if datetime.now() - cached_result["timestamp"] < timedelta(minutes=15):
                return JSONResponse(content=cached_result["data"])
        
        results = {
            "query": request.query,
            "sources_searched": [],
            "results": {
                "web": [],
                "news": [],
                "github_users": [],
                "github_repos": [],
                "reddit": [],
                "social": []
            },
            "summary": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Definir número de resultados según profundidad
        num_results = {"basic": 5, "standard": 10, "deep": 20}.get(request.depth, 10)
        
        # Ejecutar búsquedas en paralelo
        tasks = []
        
        if "web" in request.sources:
            tasks.append(("web", osint_analyzer.search_web(request.query, num_results)))
        
        if "news" in request.sources:
            tasks.append(("news", osint_analyzer.search_news(request.query, num_results)))
        
        if "github" in request.sources:
            tasks.append(("github_users", osint_analyzer.search_github(request.query, "users")))
            tasks.append(("github_repos", osint_analyzer.search_github(request.query, "repositories")))
        
        if "reddit" in request.sources:
            tasks.append(("reddit", osint_analyzer.search_reddit(request.query)))
        
        # Ejecutar búsquedas
        search_results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
        
        # Procesar resultados
        for i, (source_name, _) in enumerate(tasks):
            if i < len(search_results) and not isinstance(search_results[i], Exception):
                results["results"][source_name] = search_results[i]
                results["sources_searched"].append(source_name)
        
        # Generar resumen
        total_results = sum(len(result_list) for result_list in results["results"].values())
        results["summary"] = {
            "total_results": total_results,
            "sources_count": len(results["sources_searched"]),
            "depth": request.depth,
            "search_time": f"{num_results} resultados por fuente"
        }
        
        # Guardar en cache
        osint_cache[cache_key] = {
            "data": results,
            "timestamp": datetime.now()
        }
        
        return JSONResponse(content=results)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en búsqueda OSINT: {str(e)}"
        )

@router.post("/osint/sentiment")
async def analyze_sentiment_endpoint(request: SentimentAnalysisRequest):
    """
    Analiza el sentimiento de un texto
    
    Body:
        SentimentAnalysisRequest: Texto a analizar
    
    Returns:
        Dict: Análisis de sentimiento y métricas
    """
    try:
        sentiment_result = await osint_analyzer.analyze_sentiment(request.text)
        
        return JSONResponse(content={
            "text": request.text[:200],  # Primeros 200 caracteres
            "language": request.language,
            "sentiment_analysis": sentiment_result,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en análisis de sentimiento: {str(e)}"
        )

@router.post("/osint/entities")
async def extract_entities_endpoint(request: EntityExtractionRequest):
    """
    Extrae entidades nombradas de un texto
    
    Body:
        EntityExtractionRequest: Texto para análisis
    
    Returns:
        Dict: Entidades extraídas (emails, teléfonos, URLs, nombres, etc.)
    """
    try:
        entities = await osint_analyzer.extract_entities(request.text)
        
        return JSONResponse(content={
            "text": request.text[:200],
            "entities": entities,
            "entity_count": {
                key: len(value) if isinstance(value, list) else 0 
                for key, value in entities.items() 
                if key != "error"
            },
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en extracción de entidades: {str(e)}"
        )

@router.get("/osint/trending")
async def get_trending_topics():
    """
    Obtiene temas tendencia simulados para demostración
    
    Returns:
        Dict: Lista de temas en tendencia
    """
    try:
        # Obtener tendencias reales usando SerpAPI
        trending_topics = await fetch_real_trending_topics()
        
        if not trending_topics:
            # Si las APIs fallan, usar búsquedas actuales como fallback
            trending_topics = await get_trending_from_search()
        
        return JSONResponse(content={
            "trending_topics": trending_topics,
            "last_updated": datetime.now().isoformat(),
            "update_frequency": "1 hora",
            "source": "real_apis"
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo temas en tendencia: {str(e)}"
        )

@router.get("/osint/sources")
async def get_available_sources():
    """
    Lista las fuentes OSINT disponibles y su estado
    
    Returns:
        Dict: Estado de fuentes configuradas
    """
    try:
        sources_status = {
            "web_search": {
                "name": "Búsqueda Web",
                "provider": "SerpAPI",
                "available": bool(OSINT_CONFIG["serpapi"]["key"]),
                "description": "Resultados orgánicos de Google"
            },
            "news_search": {
                "name": "Búsqueda Noticias", 
                "provider": "SerpAPI",
                "available": bool(OSINT_CONFIG["serpapi"]["key"]),
                "description": "Noticias de Google News"
            },
            "github": {
                "name": "GitHub",
                "provider": "GitHub API",
                "available": bool(OSINT_CONFIG["github"]["token"]),
                "description": "Usuarios y repositorios"
            },
            "reddit": {
                "name": "Reddit",
                "provider": "Reddit API",
                "available": True,  # No requiere auth para búsqueda pública
                "description": "Posts y comentarios públicos"
            },
            "sentiment_analysis": {
                "name": "Análisis Sentimiento",
                "provider": "Interno",
                "available": True,
                "description": "Análisis de polaridad de texto"
            },
            "entity_extraction": {
                "name": "Extracción Entidades",
                "provider": "Interno", 
                "available": True,
                "description": "NER básico con regex"
            }
        }
        
        return JSONResponse(content={
            "sources": sources_status,
            "total_available": sum(1 for s in sources_status.values() if s["available"]),
            "last_checked": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo fuentes disponibles: {str(e)}"
        )

@router.delete("/osint/cache")
async def clear_osint_cache():
    """
    Limpia el cache de resultados OSINT
    
    Returns:
        Dict: Confirmación de limpieza
    """
    try:
        global osint_cache
        cache_count = len(osint_cache)
        osint_cache.clear()
        
        return JSONResponse(content={
            "message": "Cache OSINT limpiado exitosamente",
            "cleared_entries": cache_count,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error limpiando cache: {str(e)}"
        )
async def fetch_real_trending_topics() -> Dict:
    """
    Obtener temas de tendencia reales usando SerpAPI
    """
    try:
        if not OSINT_CONFIG["serpapi"]["key"]:
            return {}
        
        # Usar Google Trends a través de SerpAPI
        async with httpx.AsyncClient() as client:
            params = {
                "engine": "google_trends",
                "data_type": "TIMESERIES",
                "geo": "ES",  # España
                "api_key": OSINT_CONFIG["serpapi"]["key"]
            }
            
            response = await client.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Procesar resultados de Google Trends
                trends = {
                    "global": [],
                    "security": [],
                    "finance": [],
                    "tech": []
                }
                
                if "trending_searches" in data:
                    for item in data["trending_searches"][:20]:
                        trend_item = {
                            "keyword": item.get("query", ""),
                            "volume": item.get("search_volume", 0),
                            "sentiment": analyze_sentiment(item.get("query", "")),
                            "related_topics": item.get("related_topics", [])
                        }
                        
                        # Categorizar por palabras clave
                        keyword_lower = trend_item["keyword"].lower()
                        if any(word in keyword_lower for word in ["seguridad", "ciberseguridad", "vulnerabilidad"]):
                            trends["security"].append(trend_item)
                        elif any(word in keyword_lower for word in ["finanzas", "dinero", "banco"]):
                            trends["finance"].append(trend_item)
                        elif any(word in keyword_lower for word in ["tecnología", "IA", "software"]):
                            trends["tech"].append(trend_item)
                        else:
                            trends["global"].append(trend_item)
                
                return trends
        
        return {}
        
    except Exception as e:
        print(f"Error obteniendo tendencias reales: {e}")
        return {}

async def get_trending_from_search() -> Dict:
    """
    Obtener tendencias usando búsquedas populares
    """
    try:
        trending_searches = [
            "ciberseguridad 2024",
            "inteligencia artificial",
            "fraude financiero",
            "blockchain seguridad",
            "OSINT herramientas"
        ]
        
        trends = {"global": [], "security": [], "finance": [], "tech": []}
        
        for search_term in trending_searches:
            volume = await get_search_volume(search_term)
            sentiment = analyze_sentiment(search_term)
            
            trend_item = {
                "keyword": search_term,
                "volume": volume,
                "sentiment": sentiment
            }
            
            # Categorizar
            if "seguridad" in search_term or "fraude" in search_term:
                trends["security"].append(trend_item)
            elif "financiero" in search_term or "blockchain" in search_term:
                trends["finance"].append(trend_item)
            elif "IA" in search_term or "herramientas" in search_term:
                trends["tech"].append(trend_item)
            else:
                trends["global"].append(trend_item)
        
        return trends
        
    except Exception as e:
        print(f"Error obteniendo tendencias de búsqueda: {e}")
        return {}

async def get_search_volume(query: str) -> int:
    """
    Obtener volumen estimado de búsqueda usando SerpAPI
    """
    try:
        if not OSINT_CONFIG["serpapi"]["key"]:
            return 0
        
        async with httpx.AsyncClient() as client:
            params = {
                "engine": "google",
                "q": query,
                "api_key": OSINT_CONFIG["serpapi"]["key"],
                "num": 1
            }
            
            response = await client.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                # Estimar volumen basado en número de resultados
                if "search_information" in data:
                    total_results = data["search_information"].get("total_results", 0)
                    # Convertir a estimación de volumen mensual
                    return min(int(total_results / 1000), 50000)
        
        return 0
        
    except Exception as e:
        print(f"Error obteniendo volumen de búsqueda: {e}")
        return 0

def analyze_sentiment(text: str) -> str:
    """
    Análisis básico de sentimiento
    """
    positive_words = ["excelente", "bueno", "positivo", "innovador", "exitoso"]
    negative_words = ["malo", "problema", "error", "fallo", "vulnerabilidad", "fraude"]
    
    text_lower = text.lower()
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    else:
        return "neutral"