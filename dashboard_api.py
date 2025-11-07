"""
Dashboard API Corporativo TAVIT - API Premium para Empresas Contratantes
Sistema de búsquedas multi-fuente, seguimiento de casos y reportes con IA
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import httpx
import os
import json
import uuid
from dotenv import load_dotenv

# Importar utilidades internas
from auth import verify_token, authenticate_admin
from model_utils import ml_models
from notification_system import notification_manager

load_dotenv()

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard Corporativo"])

# Modelos de datos corporativos
class CorporateAuthRequest(BaseModel):
    company_id: str = Field(..., description="ID único de la empresa contratante")
    api_key: str = Field(..., description="Clave API empresarial")
    user_email: str = Field(..., description="Email del usuario corporativo")

class InvestigationRequest(BaseModel):
    target_name: str = Field(..., description="Nombre de la persona/empresa a investigar")
    target_id: Optional[str] = Field(None, description="Documento o ID del objetivo")
    investigation_type: str = Field(..., description="Tipo: 'fraud_detection', 'risk_assessment', 'compliance_check', 'background_investigation'")
    priority: str = Field(default="normal", description="Prioridad: low, normal, high, urgent")
    sources: List[str] = Field(default=["all"], description="Fuentes específicas o 'all' para búsqueda completa")
    company_context: Optional[str] = Field(None, description="Contexto empresarial para la investigación")

class PersonTrackingRequest(BaseModel):
    person_name: str = Field(..., description="Nombre completo de la persona")
    person_id: Optional[str] = Field(None, description="Documento de identidad")
    tracking_duration: int = Field(default=30, description="Días de seguimiento (máximo 365)")
    alert_triggers: List[str] = Field(default=["court_cases", "arrests", "bankruptcies"], description="Eventos que disparan alertas")
    notification_channels: List[str] = Field(default=["email", "webhook"], description="Canales de notificación")

class MonitoringSetupRequest(BaseModel):
    monitor_name: str = Field(..., description="Nombre del monitor")
    keywords: List[str] = Field(..., description="Palabras clave a monitorear")
    sources: List[str] = Field(..., description="Fuentes a monitorear")
    frequency: str = Field(default="daily", description="Frecuencia: hourly, daily, weekly")
    alert_threshold: int = Field(default=5, description="Número de coincidencias para activar alerta")

# Simulación de base de datos empresarial en memoria
corporate_database = {
    "companies": {},
    "investigations": {},
    "tracking_targets": {},
    "monitors": {},
    "alerts": []
}

# Fuentes OSINT avanzadas
PREMIUM_SOURCES = {
    "legal": {
        "courtlistener": "Registros judiciales federales",
        "pacer": "Sistema de casos federales",
        "vinelink": "Notificaciones penitenciarias",
        "state_courts": "Tribunales estatales",
        "bankruptcy_records": "Registros de bancarrota"
    },
    "financial": {
        "credit_bureaus": "Burós de crédito",
        "sec_filings": "Registros SEC",
        "patent_uspto": "Patentes USPTO",
        "business_registrations": "Registros empresariales",
        "tax_liens": "Gravámenes fiscales"
    },
    "social": {
        "social_media": "Redes sociales públicas",
        "professional_networks": "LinkedIn y similares",
        "news_mentions": "Menciones en noticias",
        "academic_papers": "Publicaciones académicas",
        "government_records": "Registros gubernamentales"
    },
    "technical": {
        "domain_whois": "Registros de dominios",
        "github_activity": "Actividad en GitHub",
        "technology_patents": "Patentes tecnológicas",
        "security_breaches": "Violaciones de seguridad",
        "cyber_threat_intel": "Inteligencia de amenazas"
    }
}

@router.post("/auth", summary="Autenticación corporativa")
async def corporate_auth(request: CorporateAuthRequest):
    """
    Autenticación para empresas contratantes del dashboard TAVIT
    """
    # Validar credenciales corporativas (simulado)
    if request.api_key.startswith("tavit_corp_"):
        company_info = {
            "company_id": request.company_id,
            "company_name": f"Empresa {request.company_id.upper()}",
            "plan": "Enterprise Premium",
            "monthly_searches": 10000,
            "remaining_searches": 9847,
            "features": ["multi_source_search", "ai_predictions", "real_time_monitoring", "automated_reports"],
            "access_token": f"corp_token_{uuid.uuid4().hex[:16]}"
        }
        
        corporate_database["companies"][request.company_id] = company_info
        
        return {
            "status": "authenticated",
            "company_info": company_info,
            "available_sources": len(PREMIUM_SOURCES),
            "premium_features": True
        }
    else:
        raise HTTPException(status_code=401, detail="Credenciales corporativas inválidas")

@router.post("/investigate", summary="Investigación multi-fuente completa")
async def start_investigation(
    request: InvestigationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_token)
):
    """
    Inicia una investigación completa con IA y múltiples fuentes OSINT
    """
    investigation_id = f"inv_{uuid.uuid4().hex[:12]}"
    
    # Configurar búsqueda multi-fuente
    sources_to_search = []
    if "all" in request.sources:
        sources_to_search = list(PREMIUM_SOURCES.keys())
    else:
        sources_to_search = request.sources
    
    investigation_data = {
        "id": investigation_id,
        "target_name": request.target_name,
        "target_id": request.target_id,
        "type": request.investigation_type,
        "priority": request.priority,
        "sources": sources_to_search,
        "status": "processing",
        "created_at": datetime.now().isoformat(),
        "estimated_completion": (datetime.now() + timedelta(minutes=15)).isoformat(),
        "progress": 0,
        "findings": [],
        "ai_analysis": None
    }
    
    corporate_database["investigations"][investigation_id] = investigation_data
    
    # Iniciar procesamiento en background
    background_tasks.add_task(process_investigation, investigation_id, request)
    
    return {
        "investigation_id": investigation_id,
        "status": "initiated",
        "estimated_completion_minutes": 15,
        "sources_count": len(sources_to_search),
        "tracking_url": f"/api/v1/dashboard/investigation/{investigation_id}/status"
    }

@router.get("/investigation/{investigation_id}/status", summary="Estado de investigación")
async def get_investigation_status(investigation_id: str):
    """
    Obtiene el estado actual de una investigación en curso
    """
    if investigation_id not in corporate_database["investigations"]:
        raise HTTPException(status_code=404, detail="Investigación no encontrada")
    
    investigation = corporate_database["investigations"][investigation_id]
    return investigation

@router.get("/cases", summary="Lista de casos activos")
async def get_active_cases(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50
):
    """
    Obtiene lista de casos/investigaciones activas
    """
    cases = list(corporate_database["investigations"].values())
    
    # Filtros
    if status:
        cases = [c for c in cases if c["status"] == status]
    if priority:
        cases = [c for c in cases if c["priority"] == priority]
    
    # Limitar resultados
    cases = cases[:limit]
    
    return {
        "total_cases": len(cases),
        "active_investigations": len([c for c in cases if c["status"] == "processing"]),
        "completed_investigations": len([c for c in cases if c["status"] == "completed"]),
        "cases": cases
    }

@router.post("/track-person", summary="Seguimiento de persona en tiempo real")
async def setup_person_tracking(
    request: PersonTrackingRequest,
    background_tasks: BackgroundTasks
):
    """
    Configura seguimiento automático de una persona con alertas
    """
    tracking_id = f"track_{uuid.uuid4().hex[:12]}"
    
    tracking_config = {
        "id": tracking_id,
        "person_name": request.person_name,
        "person_id": request.person_id,
        "duration_days": request.tracking_duration,
        "alert_triggers": request.alert_triggers,
        "notification_channels": request.notification_channels,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "last_check": None,
        "alerts_generated": 0,
        "data_points_collected": 0
    }
    
    corporate_database["tracking_targets"][tracking_id] = tracking_config
    
    # Iniciar monitoreo automático
    background_tasks.add_task(start_person_monitoring, tracking_id)
    
    return {
        "tracking_id": tracking_id,
        "status": "tracking_initiated",
        "duration_days": request.tracking_duration,
        "next_check": (datetime.now() + timedelta(hours=1)).isoformat(),
        "alert_triggers": request.alert_triggers
    }

@router.get("/reports/{case_id}", summary="Reporte detallado con IA")
async def generate_detailed_report(case_id: str):
    """
    Genera reporte detallado con análisis de IA para un caso específico
    """
    if case_id not in corporate_database["investigations"]:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    
    investigation = corporate_database["investigations"][case_id]
    
    # Generar reporte con IA (simulado)
    ai_report = {
        "executive_summary": f"Análisis completo de {investigation['target_name']} realizado mediante 25+ fuentes OSINT y modelos de IA CatBoost.",
        "risk_assessment": {
            "overall_risk": "MEDIUM",
            "risk_score": 67,
            "risk_factors": [
                "Historial crediticio irregular detectado",
                "Menciones en redes sociales con patrones atípicos",
                "No se encontraron registros judiciales adversos"
            ]
        },
        "fraud_indicators": {
            "fraud_probability": 23.5,
            "indicators_found": [
                "Inconsistencias en información de contacto",
                "Actividad en redes sociales limitada para el perfil declarado"
            ]
        },
        "legal_findings": {
            "court_cases": 0,
            "bankruptcy_records": 0,
            "tax_liens": 1,
            "regulatory_actions": 0
        },
        "social_footprint": {
            "social_media_presence": "Limited",
            "professional_networks": "Active on LinkedIn",
            "news_mentions": 3,
            "reputation_score": 78
        },
        "recommendations": [
            "Solicitar documentación adicional para verificar inconsistencias",
            "Implementar monitoreo continuo por 90 días",
            "Revisar información de ingresos declarados"
        ],
        "confidence_level": 0.84,
        "data_sources_used": 18,
        "generated_at": datetime.now().isoformat()
    }
    
    return {
        "case_id": case_id,
        "report_type": "comprehensive_ai_analysis",
        "target_name": investigation["target_name"],
        "ai_analysis": ai_report,
        "raw_data_points": len(investigation.get("findings", [])),
        "processing_time_minutes": 12,
        "report_url": f"/api/v1/dashboard/reports/{case_id}/download"
    }

@router.post("/monitor", summary="Configurar monitoreo automático")
async def setup_monitoring(request: MonitoringSetupRequest):
    """
    Configura monitoreo automático de palabras clave en múltiples fuentes
    """
    monitor_id = f"mon_{uuid.uuid4().hex[:12]}"
    
    monitor_config = {
        "id": monitor_id,
        "name": request.monitor_name,
        "keywords": request.keywords,
        "sources": request.sources,
        "frequency": request.frequency,
        "alert_threshold": request.alert_threshold,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "last_run": None,
        "alerts_triggered": 0,
        "matches_found": 0
    }
    
    corporate_database["monitors"][monitor_id] = monitor_config
    
    return {
        "monitor_id": monitor_id,
        "status": "monitoring_active",
        "keywords_count": len(request.keywords),
        "sources_count": len(request.sources),
        "frequency": request.frequency,
        "next_check": (datetime.now() + timedelta(hours=1)).isoformat()
    }

@router.get("/alerts", summary="Alertas activas del sistema")
async def get_system_alerts(
    severity: Optional[str] = None,
    limit: int = 100
):
    """
    Obtiene alertas activas del sistema de monitoreo
    """
    alerts = corporate_database["alerts"]
    
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    
    alerts = alerts[:limit]
    
    return {
        "total_alerts": len(alerts),
        "critical_alerts": len([a for a in alerts if a.get("severity") == "critical"]),
        "warning_alerts": len([a for a in alerts if a.get("severity") == "warning"]),
        "info_alerts": len([a for a in alerts if a.get("severity") == "info"]),
        "alerts": alerts
    }

# Funciones de procesamiento en background
async def process_investigation(investigation_id: str, request: InvestigationRequest):
    """
    Procesa una investigación completa en background
    """
    investigation = corporate_database["investigations"][investigation_id]
    
    # Simular procesamiento gradual
    for progress in range(0, 101, 20):
        investigation["progress"] = progress
        if progress == 100:
            investigation["status"] = "completed"
            investigation["ai_analysis"] = {
                "risk_score": 65.3,
                "fraud_probability": 18.7,
                "confidence": 0.89,
                "recommendation": "APPROVE_WITH_MONITORING"
            }
    
    # Notificar completion
    if notification_manager:
        await notification_manager.send_completion_notification(investigation_id)

async def start_person_monitoring(tracking_id: str):
    """
    Inicia monitoreo automático de una persona
    """
    tracking = corporate_database["tracking_targets"][tracking_id]
    tracking["status"] = "monitoring"
    tracking["last_check"] = datetime.now().isoformat()