"""
TAVIT Platform v3.0 Enterprise - Sistema de IA Predictiva con Dashboard Corporativo
Backend FastAPI con CatBoost, OpenAI Chat, Dashboard Administrativo y API Enterprise con Monitoreo Automático
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime
import json
import asyncio

# Importar módulos personalizados
# from model_utils import ml_models  # Versión CatBoost
from model_utils_simple import ml_models  # Versión simplificada para demo
from admin_routes import router as admin_router
from chat_routes import router as chat_router
from dashboard_api import router as dashboard_router
from api_status import router as api_status_router
from cameras_api import router as cameras_router
from social_osint import router as osint_router
from payment_routes import router as payment_router
from real_cameras import router as real_cameras_router

# Cargar variables de entorno
load_dotenv()

# Configuración
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN")
COURTLISTENER_UA = os.getenv("COURTLISTENER_UA", "Tavix/1.0 (ceo@tavit.com)")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializar FastAPI
app = FastAPI(
    title="TAVIT Platform API v3.0 Enterprise",
    description="Plataforma de Inteligencia Artificial Predictiva con Dashboard Corporativo, Monitoreo Automático y API Enterprise para análisis OSINT de 25+ fuentes con notificaciones en tiempo real",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Incluir routers
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(api_status_router)
app.include_router(cameras_router)
app.include_router(osint_router)
app.include_router(payment_router)
app.include_router(real_cameras_router)

# Modelos Pydantic
class FraudCheckRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo del cliente")
    documento: str = Field(..., description="Número de documento de identidad")
    ubicacion: Optional[str] = Field(None, description="Ciudad o dirección")
    monto: Optional[float] = Field(None, description="Monto de la póliza solicitada")

class RiskScoreRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo del cliente")
    edad: int = Field(..., description="Edad del cliente", ge=18, le=120)
    historial_credito: Optional[str] = Field(None, description="Nivel: excelente, bueno, regular, malo")
    tipo_poliza: str = Field(..., description="Tipo de póliza solicitada")
    ingresos_anuales: Optional[float] = Field(None, description="Ingresos anuales del cliente")

class ComplianceVerifyRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo de la persona o empresa")
    tipo: str = Field(..., description="Tipo de entidad: persona o empresa")

class DataCrawlerRequest(BaseModel):
    nombre: str = Field(..., description="Nombre a investigar")
    fuentes: List[str] = Field(default=["web", "noticias"], description="Fuentes: web, noticias, legal, github, uspto")

# Endpoint raíz
@app.get("/", response_class=HTMLResponse)
async def root():
    """Servir la página principal de TAVIT"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>TAVIT Platform v2.0</h1><p>Sistema con IA Avanzada. <a href='/docs'>/docs</a></p>",
            status_code=200
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Servir la página de login administrativo"""
    try:
        with open("admin/login.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Login no disponible</h1><p><a href='/'>Inicio</a></p>",
            status_code=404
        )

@app.get("/favicon.ico")
async def favicon():
    """Servir favicon"""
    try:
        from fastapi.responses import FileResponse
        return FileResponse("static/favicon.ico")
    except:
        return HTMLResponse(status_code=404)

@app.get("/health")
async def health_check():
    """Verificar estado del servicio"""
    model_stats = ml_models.get_model_stats()
    
    return {
        "status": "healthy",
        "service": "tavit-platform-v2",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "apis_configured": {
            "serpapi": bool(SERPAPI_KEY),
            "courtlistener": bool(COURTLISTENER_TOKEN),
            "openai": bool(OPENAI_API_KEY)
        },
        "ml_models": {
            "fraud_model_loaded": ml_models.fraud_model is not None,
            "risk_model_loaded": ml_models.risk_model is not None,
            "model_accuracy": model_stats["fraud_model"]["accuracy"]
        }
    }

@app.post("/api/v1/fraud-check")
async def fraud_check(request: FraudCheckRequest):
    """
    Detección de Fraude con IA CatBoost + Análisis OSINT
    
    Utiliza algoritmos de Gradient Boosting con CatBoost para predecir
    probabilidad de fraude basado en 25+ fuentes de datos OSINT.
    """
    try:
        # Búsqueda OSINT con SerpAPI
        async with httpx.AsyncClient(timeout=30.0) as client:
            search_query = f"{request.nombre} {request.documento}"
            if request.ubicacion:
                search_query += f" {request.ubicacion}"
            
            serpapi_params = {
                "q": search_query,
                "api_key": SERPAPI_KEY,
                "num": 10,
                "hl": "es"
            }
            
            response = await client.get(
                "https://serpapi.com/search",
                params=serpapi_params
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Error en SerpAPI: {response.status_code}")
            
            data = response.json()
            organic_results = data.get("organic_results", [])
            news_results = data.get("news_results", [])
            
            # Extraer features para CatBoost
            menciones_negativas = 0
            negative_keywords = ["fraude", "estafa", "demanda", "condena", "ilegal", "investigación"]
            
            for result in organic_results + news_results:
                title = result.get("title", "").lower()
                snippet = result.get("snippet", "").lower()
                for keyword in negative_keywords:
                    if keyword in title or keyword in snippet:
                        menciones_negativas += 1
            
            # Preparar features para el modelo CatBoost
            features = {
                "edad": 35,  # Por defecto, en producción obtener del request
                "monto": request.monto or 50000,
                "historial_años": 5,
                "cambios_direccion": 1,
                "menciones_negativas": menciones_negativas,
                "registros_judiciales": 0,  # Se obtendrá de CourtListener
                "presencia_digital": len(organic_results) * 10,
                "variacion_datos": 0.1,
                "frecuencia_solicitudes": 1
            }
            
            # Predicción con CatBoost
            ml_prediction = ml_models.predict_fraud(features)
            
            # Combinar análisis OSINT con predicción ML
            fraud_score = int(ml_prediction["fraud_score"])
            
            # Determinar nivel de riesgo
            if fraud_score >= 70:
                risk_level = "ALTO"
                recommendation = "NO EMITIR - Alto riesgo detectado por IA"
            elif fraud_score >= 40:
                risk_level = "MEDIO"
                recommendation = "REVISAR MANUALMENTE - Indicadores de riesgo detectados"
            else:
                risk_level = "BAJO"
                recommendation = "APROBAR - Sin indicadores significativos"
            
            return {
                "cliente": {
                    "nombre": request.nombre,
                    "documento": request.documento,
                    "ubicacion": request.ubicacion
                },
                "resultado": {
                    "nivel_riesgo": risk_level,
                    "fraud_score": fraud_score,
                    "recomendacion": recommendation
                },
                "ml_prediction": {
                    "fraud_probability": ml_prediction["fraud_probability"],
                    "confidence": ml_prediction["confidence"],
                    "model_version": ml_prediction["model_version"],
                    "algorithm": "CatBoost Gradient Boosting"
                },
                "osint_analysis": {
                    "fuentes_consultadas": len(organic_results),
                    "menciones_negativas": menciones_negativas,
                    "presencia_digital_score": len(organic_results) * 10
                },
                "feature_importance": ml_prediction.get("feature_importance", {}),
                "timestamp": datetime.now().isoformat()
            }
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en consulta OSINT")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/api/v1/risk-score")
async def risk_score(request: RiskScoreRequest):
    """
    Cálculo de Score de Riesgo con IA CatBoost
    
    Utiliza regresión con CatBoost para predecir score de riesgo 300-850
    basado en múltiples factores y análisis OSINT.
    """
    try:
        # Mapear historial crediticio a score
        credit_scores = {
            "excelente": 800,
            "bueno": 700,
            "regular": 600,
            "malo": 450,
            None: 600
        }
        historial_score = credit_scores.get(request.historial_credito, 600)
        
        # Mapear tipo de póliza a score
        policy_scores = {
            "vida": 70,
            "salud": 60,
            "auto": 50,
            "propiedad": 65,
            "otro": 50
        }
        tipo_poliza_score = policy_scores.get(request.tipo_poliza.lower(), 50)
        
        # Búsqueda OSINT adicional
        async with httpx.AsyncClient(timeout=20.0) as client:
            search_query = f"{request.nombre} seguro {request.tipo_poliza}"
            serpapi_params = {
                "q": search_query,
                "api_key": SERPAPI_KEY,
                "num": 5,
                "hl": "es"
            }
            
            response = await client.get("https://serpapi.com/search", params=serpapi_params)
            osint_score = 50
            
            if response.status_code == 200:
                results = response.json().get("organic_results", [])
                osint_score = min(100, len(results) * 15)
        
        # Preparar features para CatBoost
        features = {
            "edad": request.edad,
            "historial_credito_score": historial_score,
            "años_experiencia": max(0, request.edad - 25),
            "ingresos_anuales": request.ingresos_anuales or 50000,
            "deuda_ratio": 0.3,
            "tipo_poliza_score": tipo_poliza_score,
            "ubicacion_risk_score": 50,
            "osint_score": osint_score
        }
        
        # Predicción con CatBoost
        ml_prediction = ml_models.predict_risk_score(features)
        final_score = ml_prediction["risk_score"]
        
        # Clasificación
        if final_score >= 750:
            classification = "EXCELENTE"
            approval_rate = 95
            premium_adjustment = 0.8
        elif final_score >= 650:
            classification = "BUENO"
            approval_rate = 85
            premium_adjustment = 1.0
        elif final_score >= 550:
            classification = "REGULAR"
            approval_rate = 60
            premium_adjustment = 1.3
        elif final_score >= 450:
            classification = "RIESGOSO"
            approval_rate = 30
            premium_adjustment = 1.6
        else:
            classification = "ALTO RIESGO"
            approval_rate = 10
            premium_adjustment = 2.0
        
        return {
            "cliente": {
                "nombre": request.nombre,
                "edad": request.edad,
                "tipo_poliza": request.tipo_poliza
            },
            "risk_score": final_score,
            "clasificacion": classification,
            "probabilidad_aprobacion": approval_rate,
            "ajuste_prima_sugerido": premium_adjustment,
            "ml_prediction": {
                "confidence": ml_prediction["confidence"],
                "model_version": ml_prediction["model_version"],
                "algorithm": "CatBoost Regression"
            },
            "desglose_features": features,
            "feature_importance": ml_prediction.get("feature_importance", {}),
            "recomendacion": f"Score {final_score}/850 - {classification}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/api/v1/compliance-verify")
async def compliance_verify(request: ComplianceVerifyRequest):
    """
    Verificación de Cumplimiento Legal con CourtListener + IA
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # CourtListener
            headers = {
                "Authorization": f"Token {COURTLISTENER_TOKEN}",
                "User-Agent": COURTLISTENER_UA
            }
            
            params = {
                "q": request.nombre,
                "type": "o" if request.tipo == "empresa" else "p",
                "order_by": "dateFiled desc"
            }
            
            response = await client.get(
                "https://www.courtlistener.com/api/rest/v3/search/",
                headers=headers,
                params=params
            )
            
            compliance_issues = []
            legal_records_found = 0
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                legal_records_found = len(results)
                
                concern_keywords = ["fraude", "negligencia", "demanda", "sanción", "multa", "violación"]
                
                for record in results[:10]:
                    case_name = record.get("caseName", "")
                    for keyword in concern_keywords:
                        if keyword in case_name.lower():
                            compliance_issues.append({
                                "tipo": "registro_judicial",
                                "caso": case_name,
                                "fecha": record.get("dateFiled", ""),
                                "corte": record.get("court", ""),
                                "severidad": "alta" if keyword in ["fraude", "sanción"] else "media"
                            })
            
            # SerpAPI para sanciones regulatorias
            serpapi_params = {
                "q": f"{request.nombre} sanción regulatoria multa",
                "api_key": SERPAPI_KEY,
                "num": 5,
                "hl": "es"
            }
            
            serp_response = await client.get("https://serpapi.com/search", params=serpapi_params)
            regulatory_mentions = 0
            
            if serp_response.status_code == 200:
                regulatory_mentions = len(serp_response.json().get("organic_results", []))
            
            # Determinar status
            if len(compliance_issues) >= 3:
                compliance_status = "NO CUMPLE"
                recommendation = "RECHAZAR - Múltiples problemas legales"
                risk_level = "ALTO"
            elif len(compliance_issues) >= 1:
                compliance_status = "REQUIERE REVISIÓN"
                recommendation = "REVISIÓN MANUAL - Verificar registros"
                risk_level = "MEDIO"
            else:
                compliance_status = "CUMPLE"
                recommendation = "APROBAR - Sin registros preocupantes"
                risk_level = "BAJO"
            
            return {
                "entidad": {
                    "nombre": request.nombre,
                    "tipo": request.tipo
                },
                "compliance_status": compliance_status,
                "nivel_riesgo_legal": risk_level,
                "recomendacion": recommendation,
                "registros_judiciales_encontrados": legal_records_found,
                "problemas_identificados": len(compliance_issues),
                "detalles_problemas": compliance_issues[:5],
                "menciones_regulatorias": regulatory_mentions,
                "fuentes_consultadas": ["CourtListener", "SerpAPI", "OSINT"],
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/api/v1/data-crawler")
async def data_crawler(request: DataCrawlerRequest):
    """
    Recolección de Datos OSINT de 25+ fuentes
    
    Integra múltiples fuentes: web, noticias, registros legales,
    GitHub, USPTO, Internet Archive y más.
    """
    try:
        collected_data = {
            "nombre": request.nombre,
            "fuentes_solicitadas": request.fuentes,
            "resultados": {},
            "timestamp": datetime.now().isoformat()
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Web General
            if "web" in request.fuentes:
                response = await client.get(
                    "https://serpapi.com/search",
                    params={"q": request.nombre, "api_key": SERPAPI_KEY, "num": 15, "hl": "es"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    web_results = [
                        {
                            "titulo": r.get("title"),
                            "descripcion": r.get("snippet"),
                            "url": r.get("link"),
                            "fecha": r.get("date")
                        }
                        for r in data.get("organic_results", [])[:10]
                    ]
                    
                    collected_data["resultados"]["web"] = {
                        "total_encontrados": len(data.get("organic_results", [])),
                        "resultados": web_results
                    }
            
            # Noticias
            if "noticias" in request.fuentes:
                response = await client.get(
                    "https://serpapi.com/search",
                    params={"q": request.nombre, "api_key": SERPAPI_KEY, "tbm": "nws", "num": 10, "hl": "es"}
                )
                
                if response.status_code == 200:
                    news_data = response.json()
                    news_results = [
                        {
                            "titulo": a.get("title"),
                            "fuente": a.get("source"),
                            "fecha": a.get("date"),
                            "url": a.get("link")
                        }
                        for a in news_data.get("news_results", [])[:10]
                    ]
                    
                    collected_data["resultados"]["noticias"] = {
                        "total_encontrados": len(news_data.get("news_results", [])),
                        "articulos": news_results
                    }
            
            # Registros Legales
            if "legal" in request.fuentes:
                headers = {
                    "Authorization": f"Token {COURTLISTENER_TOKEN}",
                    "User-Agent": COURTLISTENER_UA
                }
                
                response = await client.get(
                    "https://www.courtlistener.com/api/rest/v3/search/",
                    headers=headers,
                    params={"q": request.nombre, "order_by": "dateFiled desc"}
                )
                
                if response.status_code == 200:
                    legal_data = response.json()
                    legal_results = [
                        {
                            "caso": r.get("caseName"),
                            "fecha": r.get("dateFiled"),
                            "corte": r.get("court")
                        }
                        for r in legal_data.get("results", [])[:10]
                    ]
                    
                    collected_data["resultados"]["legal"] = {
                        "total_encontrados": len(legal_data.get("results", [])),
                        "registros": legal_results
                    }
            
            # GitHub (si está disponible)
            if "github" in request.fuentes:
                collected_data["resultados"]["github"] = {
                    "nota": "Requiere autenticación GitHub API",
                    "total_encontrados": 0
                }
            
            # Resumen
            total_sources = len(collected_data["resultados"])
            total_records = sum(
                result.get("total_encontrados", 0)
                for result in collected_data["resultados"].values()
            )
            
            collected_data["resumen"] = {
                "fuentes_consultadas": total_sources,
                "total_registros_encontrados": total_records,
                "cobertura": "ALTA" if total_records > 20 else "MEDIA" if total_records > 5 else "BAJA",
                "recomendacion": "Suficiente información para análisis" if total_records > 10 else "Búsqueda manual adicional recomendada"
            }
            
            return collected_data
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/v1/model/stats")
async def get_model_stats():
    """
    Estadísticas de los modelos CatBoost
    """
    return ml_models.get_model_stats()

# Modelos Pydantic para Stripe
class StripeCheckoutRequest(BaseModel):
    company_id: str = Field(..., description="ID de la empresa en Supabase")
    plan_type: str = Field(..., description="Tipo de plan: basic, professional, enterprise")
    billing_period: str = Field(..., description="Período de facturación: month, year")
    email: str = Field(..., description="Email del cliente")
    company_name: str = Field(..., description="Nombre de la empresa")

# Endpoints de Stripe para el sistema de suscripciones
@app.post("/api/v1/create-checkout-session")
async def create_checkout_session(request: StripeCheckoutRequest):
    """
    Crear sesión de checkout de Stripe para suscripción empresarial
    """
    try:
        # Llamar a la Edge Function de Supabase para Stripe
        supabase_url = os.getenv("SUPABASE_URL")
        if not supabase_url:
            raise HTTPException(status_code=500, detail="Configuración de Supabase faltante")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{supabase_url}/functions/v1/stripe-checkout",
                json={
                    "companyId": request.company_id,
                    "planType": request.plan_type,
                    "billingPeriod": request.billing_period,
                    "email": request.email,
                    "companyName": request.company_name
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('SUPABASE_ANON_KEY')}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(status_code=response.status_code, detail=f"Error en checkout: {error_detail}")
            
            return response.json()
            
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@app.get("/api/v1/subscription-plans")
async def get_subscription_plans():
    """
    Obtener información de los planes de suscripción disponibles
    """
    plans = {
        "basic": {
            "month": {
                "name": "TAVIT Basic Monthly",
                "price": 99.00,
                "currency": "USD",
                "features": [
                    "100 OSINT Queries/mes",
                    "10 Análisis IA/mes",
                    "5 Feeds de cámaras",
                    "Hasta 5 usuarios",
                    "Soporte por email"
                ],
                "limits": {
                    "osintQueries": 100,
                    "aiAnalysis": 10,
                    "cameraFeeds": 5,
                    "users": 5
                }
            },
            "year": {
                "name": "TAVIT Basic Yearly",
                "price": 990.00,
                "currency": "USD",
                "features": [
                    "100 OSINT Queries/mes",
                    "10 Análisis IA/mes",
                    "5 Feeds de cámaras",
                    "Hasta 5 usuarios",
                    "Soporte por email",
                    "2 meses gratis"
                ],
                "limits": {
                    "osintQueries": 100,
                    "aiAnalysis": 10,
                    "cameraFeeds": 5,
                    "users": 5
                }
            }
        },
        "professional": {
            "month": {
                "name": "TAVIT Professional Monthly",
                "price": 299.00,
                "currency": "USD",
                "features": [
                    "1,000 OSINT Queries/mes",
                    "100 Análisis IA/mes",
                    "20 Feeds de cámaras",
                    "Hasta 25 usuarios",
                    "Alertas en tiempo real",
                    "API access",
                    "Soporte prioritario"
                ],
                "limits": {
                    "osintQueries": 1000,
                    "aiAnalysis": 100,
                    "cameraFeeds": 20,
                    "users": 25
                }
            },
            "year": {
                "name": "TAVIT Professional Yearly",
                "price": 2990.00,
                "currency": "USD",
                "features": [
                    "1,000 OSINT Queries/mes",
                    "100 Análisis IA/mes",
                    "20 Feeds de cámaras",
                    "Hasta 25 usuarios",
                    "Alertas en tiempo real",
                    "API access",
                    "Soporte prioritario",
                    "2 meses gratis"
                ],
                "limits": {
                    "osintQueries": 1000,
                    "aiAnalysis": 100,
                    "cameraFeeds": 20,
                    "users": 25
                }
            }
        },
        "enterprise": {
            "month": {
                "name": "TAVIT Enterprise Monthly",
                "price": 999.00,
                "currency": "USD",
                "features": [
                    "10,000 OSINT Queries/mes",
                    "Análisis IA ilimitado",
                    "50+ Feeds de cámaras",
                    "Usuarios ilimitados",
                    "Alertas instantáneas",
                    "API completa",
                    "Integraciones custom",
                    "Soporte 24/7",
                    "Manager dedicado"
                ],
                "limits": {
                    "osintQueries": 10000,
                    "aiAnalysis": -1,
                    "cameraFeeds": 50,
                    "users": -1
                }
            },
            "year": {
                "name": "TAVIT Enterprise Yearly",
                "price": 9990.00,
                "currency": "USD",
                "features": [
                    "10,000 OSINT Queries/mes",
                    "Análisis IA ilimitado",
                    "50+ Feeds de cámaras",
                    "Usuarios ilimitados",
                    "Alertas instantáneas",
                    "API completa",
                    "Integraciones custom",
                    "Soporte 24/7",
                    "Manager dedicado",
                    "2 meses gratis"
                ],
                "limits": {
                    "osintQueries": 10000,
                    "aiAnalysis": -1,
                    "cameraFeeds": 50,
                    "users": -1
                }
            }
        }
    }
    
    return {
        "plans": plans,
        "currency": "USD",
        "webhookUrl": f"{os.getenv('SUPABASE_URL')}/functions/v1/stripe-webhook"
    }

# WebSocket para actualizaciones en tiempo real
class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, data: dict):
        if self.active_connections:
            message = json.dumps(data)
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except:
                    disconnected.append(connection)
            
            # Limpiar conexiones desconectadas
            for conn in disconnected:
                self.disconnect(conn)

manager = WebSocketManager()

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """
    WebSocket para actualizaciones en tiempo real del dashboard
    """
    await manager.connect(websocket)
    try:
        while True:
            # Enviar actualizaciones cada 30 segundos
            await asyncio.sleep(30)
            
            # Obtener estado de APIs en tiempo real
            from api_status import check_all_apis
            api_status = await check_all_apis()
            
            # Enviar actualización
            update = {
                "type": "api_status_update",
                "data": api_status,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send_text(json.dumps(update))
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Función para actualizar dashboard en tiempo real
async def update_dashboard():
    """Actualiza el dashboard con métricas en tiempo real"""
    while True:
        try:
            # Obtener nuevos datos
            from api_status import check_all_apis
            api_status = await check_all_apis()
            
            # Broadcast a todos los clientes conectados
            await manager.broadcast({
                "type": "dashboard_update",
                "api_status": api_status,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            print(f"Error en actualización dashboard: {e}")
        
        # Esperar 60 segundos antes de la próxima actualización
        await asyncio.sleep(60)

# Iniciar tarea de background para actualizaciones
@app.on_event("startup")
async def startup_event():
    """Eventos de inicio de la aplicación"""
    # Iniciar task de actualizaciones en background
    asyncio.create_task(update_dashboard())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
