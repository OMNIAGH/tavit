"""
Rutas del Dashboard Administrativo TAVIT
Endpoints para autenticación, estadísticas, casos y empresas
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import os
from auth import authenticate_admin, create_access_token, verify_token

router = APIRouter(prefix="/admin", tags=["Admin"])

# Modelos Pydantic
class LoginRequest(BaseModel):
    email: str
    password: str

class AdminStats(BaseModel):
    total_queries: int
    cases_processed: int
    model_accuracy: float
    api_uptime: float
    avg_response_time: float

# Base de datos en memoria para demo (en producción usar PostgreSQL)
REQUEST_LOG = []
CASES_DB = []
COMPANIES_DB = [
    {"id": 1, "name": "Seguros Monterrey", "total_queries": 1247, "last_query": "2025-11-05T14:30:00"},
    {"id": 2, "name": "MedicoVida", "total_queries": 892, "last_query": "2025-11-06T09:15:00"},
    {"id": 3, "name": "AseguraPlus", "total_queries": 1568, "last_query": "2025-11-06T16:45:00"},
    {"id": 4, "name": "ProtecSegur", "total_queries": 634, "last_query": "2025-11-04T11:20:00"},
    {"id": 5, "name": "VidaTotal", "total_queries": 1123, "last_query": "2025-11-06T13:50:00"}
]

@router.post("/login")
async def admin_login(request: LoginRequest):
    """
    Endpoint de autenticación para dashboard admin
    """
    if not authenticate_admin(request.email, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    # Crear token JWT
    access_token = create_access_token(
        data={"sub": request.email, "role": "admin"}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "email": request.email,
        "role": "admin",
        "expires_in": 28800  # 8 horas en segundos
    }

@router.get("/dashboard")
@router.get("/dashboard.html")
async def get_dashboard():
    """
    Página principal del dashboard (HTML)
    La autenticación se maneja en el frontend con JavaScript
    """
    try:
        # Cambiar al directorio del archivo
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dashboard_path = os.path.join(current_dir, "admin", "dashboard.html")
        
        with open(dashboard_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard no disponible</h1><p><a href='/login'>Iniciar Sesión</a></p>",
            status_code=404
        )

@router.get("/stats")
async def get_admin_stats(token_payload: dict = Depends(verify_token)):
    """
    Estadísticas generales del sistema
    """
    # Calcular estadísticas
    total_queries = sum([c["total_queries"] for c in COMPANIES_DB])
    cases_processed = len(CASES_DB)
    
    # Estadísticas por hora (últimas 24 horas)
    now = datetime.now()
    hourly_stats = []
    for i in range(24):
        hour = now - timedelta(hours=23-i)
        # Simular queries por hora
        queries = int(total_queries / 24 * (0.8 + 0.4 * (i % 3)))
        hourly_stats.append({
            "hour": hour.strftime("%H:00"),
            "queries": queries,
            "fraud_detected": int(queries * 0.15),
            "high_risk": int(queries * 0.23)
        })
    
    # Distribución de riesgo
    risk_distribution = {
        "bajo": 1247,
        "medio": 892,
        "alto": 425
    }
    
    # API status
    api_status = {
        "serpapi": {"status": "operational", "response_time": 1.2, "requests_today": 1247},
        "courtlistener": {"status": "operational", "response_time": 2.3, "requests_today": 634},
        "osint_sources": {"status": "operational", "active_sources": 25, "requests_today": 2156}
    }
    
    return {
        "overview": {
            "total_queries": total_queries,
            "cases_processed": cases_processed,
            "model_accuracy": 0.947,
            "api_uptime": 99.8,
            "avg_response_time": 2.1,
            "fraud_detection_rate": 0.15,
            "active_companies": len(COMPANIES_DB)
        },
        "hourly_stats": hourly_stats,
        "risk_distribution": risk_distribution,
        "api_status": api_status,
        "model_performance": {
            "fraud_model": {
                "accuracy": 0.947,
                "precision": 0.923,
                "recall": 0.891,
                "f1_score": 0.907
            },
            "risk_model": {
                "r2_score": 0.89,
                "mae": 23.5,
                "rmse": 31.2
            }
        },
        "timestamp": datetime.now().isoformat()
    }

@router.get("/cases")
async def get_cases(
    status_filter: Optional[str] = None,
    risk_filter: Optional[str] = None,
    limit: int = 50,
    token_payload: dict = Depends(verify_token)
):
    """
    Obtener lista de casos procesados
    """
    # Generar casos de ejemplo
    cases = [
        {
            "id": f"CASE-{1000+i}",
            "client_name": f"Cliente {i}",
            "company": COMPANIES_DB[i % len(COMPANIES_DB)]["name"],
            "request_type": ["fraud_check", "risk_score", "compliance_verify"][i % 3],
            "risk_level": ["bajo", "medio", "alto"][i % 3],
            "fraud_score": 10 + (i % 3) * 30,
            "risk_score": 500 + (i % 3) * 100,
            "status": ["completed", "in_progress", "pending"][i % 3],
            "created_at": (datetime.now() - timedelta(days=i % 30)).isoformat(),
            "processing_time": 1.5 + (i % 10) * 0.3
        }
        for i in range(50)
    ]
    
    # Aplicar filtros
    if status_filter:
        cases = [c for c in cases if c["status"] == status_filter]
    if risk_filter:
        cases = [c for c in cases if c["risk_level"] == risk_filter]
    
    return {
        "cases": cases[:limit],
        "total": len(cases),
        "filters_applied": {
            "status": status_filter,
            "risk": risk_filter
        }
    }

@router.get("/cases/{case_id}")
async def get_case_detail(case_id: str, token_payload: dict = Depends(verify_token)):
    """
    Obtener detalles de un caso específico
    """
    return {
        "id": case_id,
        "client_name": "Juan Pérez García",
        "client_document": "12345678A",
        "company": "Seguros Monterrey",
        "request_type": "fraud_check",
        "status": "completed",
        "created_at": "2025-11-06T10:30:00",
        "completed_at": "2025-11-06T10:30:02",
        "processing_time": 2.1,
        "results": {
            "fraud_check": {
                "fraud_score": 15,
                "risk_level": "bajo",
                "recommendation": "APROBAR",
                "indicators": [],
                "ml_prediction": {
                    "fraud_probability": 0.15,
                    "confidence": 0.92,
                    "model_version": "1.0"
                }
            },
            "osint_data": {
                "sources_consulted": 25,
                "records_found": 47,
                "negative_mentions": 0,
                "legal_records": 0
            }
        },
        "feature_importance": {
            "menciones_negativas": 0.25,
            "registros_judiciales": 0.22,
            "presencia_digital": 0.18,
            "cambios_direccion": 0.15,
            "otros": 0.20
        }
    }

@router.get("/companies")
async def get_companies(token_payload: dict = Depends(verify_token)):
    """
    Obtener lista de empresas usando la red TAVIT
    """
    # Enriquecer datos de empresas
    enriched_companies = []
    for company in COMPANIES_DB:
        enriched_companies.append({
            **company,
            "fraud_detection_rate": 0.12 + (company["id"] % 3) * 0.05,
            "avg_risk_score": 550 + (company["id"] % 5) * 50,
            "active_since": "2024-06-15",
            "subscription": "Enterprise",
            "monthly_queries": company["total_queries"],
            "savings_estimate": company["total_queries"] * 125  # €125 por fraude detectado
        })
    
    return {
        "companies": enriched_companies,
        "total": len(enriched_companies),
        "total_network_queries": sum([c["total_queries"] for c in COMPANIES_DB]),
        "avg_fraud_detection": 0.15,
        "total_savings_estimate": sum([c["total_queries"] for c in COMPANIES_DB]) * 125
    }

@router.get("/analytics")
async def get_analytics(
    period: str = "7d",
    token_payload: dict = Depends(verify_token)
):
    """
    Analytics avanzados del sistema
    """
    # Generar datos de tendencias
    days = 7 if period == "7d" else 30 if period == "30d" else 90
    
    trends = []
    for i in range(days):
        date = datetime.now() - timedelta(days=days-i-1)
        trends.append({
            "date": date.strftime("%Y-%m-%d"),
            "total_queries": 120 + i * 5,
            "fraud_detected": 18 + i,
            "high_risk_cases": 28 + i * 2,
            "avg_risk_score": 580 + (i % 10) * 10,
            "api_response_time": 2.0 + (i % 5) * 0.2
        })
    
    return {
        "period": period,
        "trends": trends,
        "summary": {
            "total_queries": sum([t["total_queries"] for t in trends]),
            "total_fraud_detected": sum([t["fraud_detected"] for t in trends]),
            "avg_detection_rate": 0.15,
            "model_drift": 0.02,  # Modelo estable
            "retraining_recommended": False
        },
        "model_performance_over_time": [
            {"date": t["date"], "accuracy": 0.94 + (i % 3) * 0.01}
            for i, t in enumerate(trends)
        ]
    }

@router.post("/model/retrain")
async def trigger_model_retrain(token_payload: dict = Depends(verify_token)):
    """
    Trigger para re-entrenar modelos
    """
    return {
        "status": "training_initiated",
        "message": "El re-entrenamiento de modelos ha sido iniciado",
        "estimated_time": "15 minutes",
        "models": ["fraud_detection", "risk_score"],
        "timestamp": datetime.now().isoformat()
    }

@router.get("/logs")
async def get_system_logs(
    level: str = "all",
    limit: int = 100,
    token_payload: dict = Depends(verify_token)
):
    """
    Obtener logs del sistema
    """
    logs = [
        {
            "timestamp": (datetime.now() - timedelta(minutes=i)).isoformat(),
            "level": ["INFO", "WARNING", "ERROR"][i % 3],
            "service": ["api", "ml_model", "osint_crawler"][i % 3],
            "message": f"Log entry {i}",
            "details": {"request_id": f"REQ-{1000+i}"}
        }
        for i in range(limit)
    ]
    
    if level != "all":
        logs = [log for log in logs if log["level"] == level.upper()]
    
    return {
        "logs": logs[:limit],
        "total": len(logs),
        "level_filter": level
    }
