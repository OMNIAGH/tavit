"""
TAVIT Platform - Sistema de Verificación de Clientes para Aseguradoras
Backend FastAPI con 4 endpoints OSINT funcionales
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import httpx
import os
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Configuración
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN")
COURTLISTENER_UA = os.getenv("COURTLISTENER_UA", "Tavix/1.0")

# Inicializar FastAPI
app = FastAPI(
    title="TAVIT Platform API",
    description="Sistema de Verificación de Clientes y Prevención de Fraude para Aseguradoras",
    version="1.0.0",
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

# Modelos Pydantic
class FraudCheckRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo del cliente")
    documento: str = Field(..., description="Número de documento de identidad")
    ubicacion: Optional[str] = Field(None, description="Ciudad o dirección")

class RiskScoreRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo del cliente")
    edad: int = Field(..., description="Edad del cliente", ge=18, le=120)
    historial_credito: Optional[str] = Field(None, description="Nivel de historial crediticio: excelente, bueno, regular, malo")
    tipo_poliza: str = Field(..., description="Tipo de póliza solicitada")

class ComplianceVerifyRequest(BaseModel):
    nombre: str = Field(..., description="Nombre completo de la persona o empresa")
    tipo: str = Field(..., description="Tipo de entidad: persona o empresa")

class DataCrawlerRequest(BaseModel):
    nombre: str = Field(..., description="Nombre a investigar")
    fuentes: List[str] = Field(default=["web", "noticias"], description="Fuentes de datos a consultar")

# Endpoint raíz - Servir index.html
@app.get("/", response_class=HTMLResponse)
async def root():
    """Servir la página principal de TAVIT"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>TAVIT Platform</h1><p>API funcionando. Visite <a href='/docs'>/docs</a> para la documentación.</p>",
            status_code=200
        )

@app.get("/health")
async def health_check():
    """Verificar estado del servicio"""
    return {
        "status": "healthy",
        "service": "tavit-platform",
        "timestamp": datetime.now().isoformat(),
        "apis_configured": {
            "serpapi": bool(SERPAPI_KEY),
            "courtlistener": bool(COURTLISTENER_TOKEN)
        }
    }

@app.post("/api/v1/fraud-check")
async def fraud_check(request: FraudCheckRequest):
    """
    Detección de Fraude mediante análisis OSINT
    
    Utiliza SerpAPI para buscar información pública sobre el cliente
    y detectar patrones sospechosos o inconsistencias.
    """
    try:
        # Buscar en SerpAPI información del cliente
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Búsqueda general
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
                raise HTTPException(
                    status_code=500,
                    detail=f"Error en SerpAPI: {response.status_code}"
                )
            
            data = response.json()
            
            # Análisis de fraude basado en resultados
            organic_results = data.get("organic_results", [])
            news_results = data.get("news_results", [])
            
            # Indicadores de riesgo
            risk_indicators = []
            fraud_score = 0
            
            # Buscar menciones en noticias negativas
            negative_keywords = ["fraude", "estafa", "demanda", "condena", "ilegal", "investigación"]
            for result in organic_results + news_results:
                title = result.get("title", "").lower()
                snippet = result.get("snippet", "").lower()
                
                for keyword in negative_keywords:
                    if keyword in title or keyword in snippet:
                        risk_indicators.append({
                            "tipo": "mencion_negativa",
                            "fuente": result.get("title"),
                            "descripcion": f"Mención de '{keyword}' encontrada",
                            "link": result.get("link")
                        })
                        fraud_score += 15
            
            # Evaluar número de resultados (muy pocos resultados = sospechoso)
            if len(organic_results) < 3:
                risk_indicators.append({
                    "tipo": "presencia_digital_limitada",
                    "descripcion": "Muy poca información disponible en línea",
                    "severidad": "media"
                })
                fraud_score += 10
            
            # Determinar nivel de riesgo
            if fraud_score >= 50:
                risk_level = "ALTO"
                recommendation = "NO EMITIR - Investigación adicional requerida"
            elif fraud_score >= 25:
                risk_level = "MEDIO"
                recommendation = "REVISAR MANUALMENTE - Requiere validación adicional"
            else:
                risk_level = "BAJO"
                recommendation = "APROBAR - Sin indicadores significativos de fraude"
            
            return {
                "cliente": {
                    "nombre": request.nombre,
                    "documento": request.documento,
                    "ubicacion": request.ubicacion
                },
                "resultado": {
                    "nivel_riesgo": risk_level,
                    "fraud_score": min(fraud_score, 100),
                    "recomendacion": recommendation
                },
                "indicadores": risk_indicators[:5],  # Top 5 indicadores
                "fuentes_consultadas": len(organic_results),
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "serpapi_resultados": len(organic_results),
                    "noticias_encontradas": len(news_results)
                }
            }
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en consulta a APIs externas")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en fraud-check: {str(e)}")

@app.post("/api/v1/risk-score")
async def risk_score(request: RiskScoreRequest):
    """
    Cálculo de Score de Riesgo
    
    Calcula un score de riesgo basado en múltiples factores:
    edad, historial crediticio, tipo de póliza, etc.
    """
    try:
        # Sistema de scoring
        base_score = 500  # Score base neutral
        
        # Factor edad (curva de riesgo por edad)
        if request.edad < 25:
            age_adjustment = -50
        elif request.edad < 35:
            age_adjustment = 20
        elif request.edad < 50:
            age_adjustment = 50
        elif request.edad < 65:
            age_adjustment = 30
        else:
            age_adjustment = -30
        
        # Factor historial crediticio
        credit_scores = {
            "excelente": 100,
            "bueno": 50,
            "regular": 0,
            "malo": -100,
            None: -20
        }
        credit_adjustment = credit_scores.get(request.historial_credito, 0)
        
        # Factor tipo de póliza (riesgo por tipo)
        policy_risk = {
            "vida": 30,
            "salud": 20,
            "auto": 10,
            "propiedad": 25,
            "otro": 0
        }
        policy_adjustment = policy_risk.get(request.tipo_poliza.lower(), 0)
        
        # Búsqueda OSINT adicional para ajustar score
        async with httpx.AsyncClient(timeout=20.0) as client:
            search_query = f"{request.nombre} seguro {request.tipo_poliza}"
            
            serpapi_params = {
                "q": search_query,
                "api_key": SERPAPI_KEY,
                "num": 5,
                "hl": "es"
            }
            
            response = await client.get(
                "https://serpapi.com/search",
                params=serpapi_params
            )
            
            osint_adjustment = 0
            if response.status_code == 200:
                data = response.json()
                results = data.get("organic_results", [])
                
                # Ajuste por menciones encontradas
                if len(results) > 5:
                    osint_adjustment = 20  # Buena presencia digital
                elif len(results) < 2:
                    osint_adjustment = -30  # Poca presencia digital
        
        # Calcular score final
        final_score = base_score + age_adjustment + credit_adjustment + policy_adjustment + osint_adjustment
        final_score = max(300, min(850, final_score))  # Rango 300-850
        
        # Clasificación de riesgo
        if final_score >= 750:
            classification = "EXCELENTE"
            approval_rate = 95
            premium_adjustment = 0.8  # 20% descuento
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
            "desglose": {
                "score_base": base_score,
                "ajuste_edad": age_adjustment,
                "ajuste_credito": credit_adjustment,
                "ajuste_poliza": policy_adjustment,
                "ajuste_osint": osint_adjustment
            },
            "recomendacion": f"Score {final_score}/850 - {classification}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en risk-score: {str(e)}")

@app.post("/api/v1/compliance-verify")
async def compliance_verify(request: ComplianceVerifyRequest):
    """
    Verificación de Cumplimiento Legal
    
    Utiliza CourtListener para verificar registros judiciales
    y validar cumplimiento regulatorio.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Búsqueda en CourtListener
            headers = {
                "Authorization": f"Token {COURTLISTENER_TOKEN}",
                "User-Agent": COURTLISTENER_UA
            }
            
            params = {
                "q": request.nombre,
                "type": "o" if request.tipo == "empresa" else "p",  # o=opinion, p=person
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
                
                # Analizar registros legales
                for record in results[:10]:  # Top 10 registros
                    case_name = record.get("caseName", "")
                    date_filed = record.get("dateFiled", "")
                    court = record.get("court", "")
                    
                    # Palabras clave de preocupación
                    concern_keywords = ["fraude", "negligencia", "demanda", "sanción", "multa", "violación"]
                    
                    for keyword in concern_keywords:
                        if keyword in case_name.lower():
                            compliance_issues.append({
                                "tipo": "registro_judicial",
                                "caso": case_name,
                                "fecha": date_filed,
                                "corte": court,
                                "severidad": "alta" if keyword in ["fraude", "sanción"] else "media"
                            })
            
            # Verificación adicional con SerpAPI para sanciones regulatorias
            serpapi_params = {
                "q": f"{request.nombre} sanción regulatoria multa",
                "api_key": SERPAPI_KEY,
                "num": 5,
                "hl": "es"
            }
            
            serp_response = await client.get(
                "https://serpapi.com/search",
                params=serpapi_params
            )
            
            regulatory_mentions = 0
            if serp_response.status_code == 200:
                serp_data = serp_response.json()
                regulatory_mentions = len(serp_data.get("organic_results", []))
            
            # Determinar status de cumplimiento
            if len(compliance_issues) >= 3:
                compliance_status = "NO CUMPLE"
                recommendation = "RECHAZAR - Múltiples problemas legales encontrados"
                risk_level = "ALTO"
            elif len(compliance_issues) >= 1:
                compliance_status = "REQUIERE REVISIÓN"
                recommendation = "REVISIÓN MANUAL - Verificar registros encontrados"
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
                "detalles_problemas": compliance_issues[:5],  # Top 5 problemas
                "menciones_regulatorias": regulatory_mentions,
                "fuentes_consultadas": ["CourtListener", "SerpAPI"],
                "timestamp": datetime.now().isoformat()
            }
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en consulta a APIs de cumplimiento")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en compliance-verify: {str(e)}")

@app.post("/api/v1/data-crawler")
async def data_crawler(request: DataCrawlerRequest):
    """
    Recolección de Datos OSINT
    
    Recopila información de múltiples fuentes públicas:
    web, noticias, redes sociales, registros públicos.
    """
    try:
        collected_data = {
            "nombre": request.nombre,
            "fuentes_solicitadas": request.fuentes,
            "resultados": {},
            "timestamp": datetime.now().isoformat()
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Búsqueda Web General
            if "web" in request.fuentes:
                serpapi_params = {
                    "q": request.nombre,
                    "api_key": SERPAPI_KEY,
                    "num": 15,
                    "hl": "es"
                }
                
                response = await client.get(
                    "https://serpapi.com/search",
                    params=serpapi_params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    web_results = []
                    
                    for result in data.get("organic_results", [])[:10]:
                        web_results.append({
                            "titulo": result.get("title"),
                            "descripcion": result.get("snippet"),
                            "url": result.get("link"),
                            "fecha": result.get("date")
                        })
                    
                    collected_data["resultados"]["web"] = {
                        "total_encontrados": len(data.get("organic_results", [])),
                        "resultados": web_results
                    }
            
            # Búsqueda de Noticias
            if "noticias" in request.fuentes:
                news_params = {
                    "q": request.nombre,
                    "api_key": SERPAPI_KEY,
                    "tbm": "nws",  # News search
                    "num": 10,
                    "hl": "es"
                }
                
                news_response = await client.get(
                    "https://serpapi.com/search",
                    params=news_params
                )
                
                if news_response.status_code == 200:
                    news_data = news_response.json()
                    news_results = []
                    
                    for article in news_data.get("news_results", [])[:10]:
                        news_results.append({
                            "titulo": article.get("title"),
                            "fuente": article.get("source"),
                            "fecha": article.get("date"),
                            "descripcion": article.get("snippet"),
                            "url": article.get("link")
                        })
                    
                    collected_data["resultados"]["noticias"] = {
                        "total_encontrados": len(news_data.get("news_results", [])),
                        "articulos": news_results
                    }
            
            # Búsqueda de Registros Legales (si solicitado)
            if "legal" in request.fuentes:
                headers = {
                    "Authorization": f"Token {COURTLISTENER_TOKEN}",
                    "User-Agent": COURTLISTENER_UA
                }
                
                legal_params = {
                    "q": request.nombre,
                    "order_by": "dateFiled desc"
                }
                
                legal_response = await client.get(
                    "https://www.courtlistener.com/api/rest/v3/search/",
                    headers=headers,
                    params=legal_params
                )
                
                if legal_response.status_code == 200:
                    legal_data = legal_response.json()
                    legal_results = []
                    
                    for record in legal_data.get("results", [])[:10]:
                        legal_results.append({
                            "caso": record.get("caseName"),
                            "fecha": record.get("dateFiled"),
                            "corte": record.get("court"),
                            "tipo": record.get("docketNumber")
                        })
                    
                    collected_data["resultados"]["legal"] = {
                        "total_encontrados": len(legal_data.get("results", [])),
                        "registros": legal_results
                    }
            
            # Análisis consolidado
            total_sources = len(collected_data["resultados"])
            total_records = sum(
                result.get("total_encontrados", 0) 
                for result in collected_data["resultados"].values()
            )
            
            collected_data["resumen"] = {
                "fuentes_consultadas": total_sources,
                "total_registros_encontrados": total_records,
                "cobertura": "ALTA" if total_records > 20 else "MEDIA" if total_records > 5 else "BAJA",
                "recomendacion": "Suficiente información para análisis" if total_records > 10 else "Se recomienda búsqueda manual adicional"
            }
            
            return collected_data
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout en recolección de datos")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en data-crawler: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
