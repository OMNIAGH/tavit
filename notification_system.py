"""
Sistema de Notificaciones Automáticas TAVIT
Integración con VINELink, PACER, CourtListener y otros sistemas de justicia
"""

import asyncio
import httpx
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning" 
    CRITICAL = "critical"
    URGENT = "urgent"

class NotificationChannel(Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"
    SLACK = "slack"

@dataclass
class Alert:
    id: str
    title: str
    message: str
    severity: AlertSeverity
    source: str
    target_person: str
    target_id: Optional[str]
    created_at: datetime
    channels: List[NotificationChannel]
    metadata: Dict[str, Any]

class NotificationManager:
    def __init__(self):
        self.alerts_queue = []
        self.active_monitors = {}
        self.notification_configs = {
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": os.getenv("NOTIFICATION_EMAIL", "alerts@tavit.com"),
                "password": os.getenv("NOTIFICATION_PASSWORD", ""),
                "from_email": "alerts@tavit.com"
            },
            "webhook": {
                "default_url": os.getenv("WEBHOOK_URL", ""),
                "timeout": 30,
                "retries": 3
            }
        }
        
        # APIs de sistemas de justicia
        self.justice_apis = {
            "courtlistener": {
                "base_url": "https://www.courtlistener.com/api/rest/v3/",
                "token": os.getenv("COURTLISTENER_TOKEN"),
                "rate_limit": 5000  # requests per hour
            },
            "pacer": {
                "base_url": "https://pcl.uscourts.gov/",
                "username": os.getenv("PACER_USERNAME", ""),
                "password": os.getenv("PACER_PASSWORD", ""),
                "rate_limit": 100
            },
            "vinelink": {
                "base_url": "https://www.vinelink.com/",
                "api_key": os.getenv("VINELINK_API_KEY", ""),
                "rate_limit": 1000
            }
        }

    async def setup_person_monitoring(self, person_name: str, person_id: str, 
                                    alert_triggers: List[str], 
                                    notification_channels: List[str]) -> str:
        """
        Configura monitoreo automático de una persona en sistemas de justicia
        """
        monitor_id = f"monitor_{person_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        monitor_config = {
            "id": monitor_id,
            "person_name": person_name,
            "person_id": person_id,
            "alert_triggers": alert_triggers,
            "channels": notification_channels,
            "active": True,
            "last_check": None,
            "check_interval": 3600,  # 1 hora
            "sources": ["courtlistener", "pacer", "vinelink", "state_courts"]
        }
        
        self.active_monitors[monitor_id] = monitor_config
        
        # Iniciar monitoreo inmediato
        await self._start_monitoring_loop(monitor_id)
        
        return monitor_id

    async def _start_monitoring_loop(self, monitor_id: str):
        """
        Inicia el bucle de monitoreo automático para una persona
        """
        monitor = self.active_monitors.get(monitor_id)
        if not monitor:
            return
        
        while monitor["active"]:
            try:
                # Verificar cada fuente de datos
                new_alerts = []
                
                # 1. CourtListener - Casos judiciales federales
                courtlistener_alerts = await self._check_courtlistener(
                    monitor["person_name"], monitor["alert_triggers"]
                )
                new_alerts.extend(courtlistener_alerts)
                
                # 2. VINELink - Notificaciones penitenciarias
                vinelink_alerts = await self._check_vinelink(
                    monitor["person_name"], monitor["person_id"]
                )
                new_alerts.extend(vinelink_alerts)
                
                # 3. PACER - Sistema de casos federales
                pacer_alerts = await self._check_pacer(
                    monitor["person_name"], monitor["alert_triggers"]
                )
                new_alerts.extend(pacer_alerts)
                
                # 4. Tribunales estatales (simulado)
                state_alerts = await self._check_state_courts(
                    monitor["person_name"], monitor["alert_triggers"]
                )
                new_alerts.extend(state_alerts)
                
                # Procesar alertas encontradas
                for alert in new_alerts:
                    await self._process_alert(alert, monitor["channels"])
                
                monitor["last_check"] = datetime.now()
                
                # Esperar hasta próxima verificación
                await asyncio.sleep(monitor["check_interval"])
                
            except Exception as e:
                error_alert = Alert(
                    id=f"error_{monitor_id}_{datetime.now().timestamp()}",
                    title="Error en Monitoreo",
                    message=f"Error monitoreando {monitor['person_name']}: {str(e)}",
                    severity=AlertSeverity.WARNING,
                    source="system",
                    target_person=monitor["person_name"],
                    target_id=monitor["person_id"],
                    created_at=datetime.now(),
                    channels=[NotificationChannel.EMAIL],
                    metadata={"monitor_id": monitor_id, "error": str(e)}
                )
                await self._process_alert(error_alert, monitor["channels"])
                
                # Esperar antes de reintentar
                await asyncio.sleep(300)  # 5 minutos

    async def _check_courtlistener(self, person_name: str, 
                                 alert_triggers: List[str]) -> List[Alert]:
        """
        Verifica nuevos casos en CourtListener
        """
        alerts = []
        
        try:
            api_config = self.justice_apis["courtlistener"]
            if not api_config["token"]:
                return alerts
            
            headers = {
                "Authorization": f"Token {api_config['token']}",
                "User-Agent": "TAVIT/1.0 (ceo@tavit.com)"
            }
            
            # Buscar opiniones recientes
            async with httpx.AsyncClient() as client:
                # Buscar por nombre en opiniones
                opinions_url = f"{api_config['base_url']}opinions/"
                params = {
                    "q": person_name,
                    "order_by": "-date_created",
                    "date_created__gte": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                }
                
                response = await client.get(opinions_url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    
                    for opinion in data.get("results", []):
                        if any(trigger in opinion.get("plain_text", "").lower() 
                              for trigger in ["arrest", "conviction", "sentence"] 
                              if trigger in alert_triggers):
                            
                            alert = Alert(
                                id=f"cl_{opinion['id']}_{datetime.now().timestamp()}",
                                title="Nuevo Caso Judicial Detectado",
                                message=f"Nueva mención de {person_name} en caso judicial: {opinion.get('case_name', 'N/A')}",
                                severity=AlertSeverity.CRITICAL,
                                source="courtlistener",
                                target_person=person_name,
                                target_id=None,
                                created_at=datetime.now(),
                                channels=[NotificationChannel.EMAIL, NotificationChannel.WEBHOOK],
                                metadata={
                                    "case_name": opinion.get("case_name"),
                                    "court": opinion.get("cluster", {}).get("docket", {}).get("court"),
                                    "date_filed": opinion.get("date_created"),
                                    "url": f"https://www.courtlistener.com{opinion.get('absolute_url', '')}"
                                }
                            )
                            alerts.append(alert)
                
        except Exception as e:
            print(f"Error checking CourtListener: {e}")
        
        return alerts

    async def _check_vinelink(self, person_name: str, person_id: str) -> List[Alert]:
        """
        Verifica notificaciones en VINELink (sistema penitenciario)
        """
        alerts = []
        
        # Simulación de verificación VINELink
        # En implementación real, se conectaría al API de VINELink
        
        # Ejemplo de alerta simulada (1% probabilidad)
        import random
        if random.random() < 0.01:  # 1% chance para demo
            alert = Alert(
                id=f"vine_{person_name.replace(' ', '_')}_{datetime.now().timestamp()}",
                title="Alerta VINELink - Cambio de Estado",
                message=f"VINELink reporta cambio de estado para {person_name}. Revisar inmediatamente.",
                severity=AlertSeverity.URGENT,
                source="vinelink",
                target_person=person_name,
                target_id=person_id,
                created_at=datetime.now(),
                channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
                metadata={
                    "facility": "Simulado - Centro Correccional",
                    "status_change": "Release Pending",
                    "notification_type": "Custody Status Change"
                }
            )
            alerts.append(alert)
        
        return alerts

    async def _check_pacer(self, person_name: str, alert_triggers: List[str]) -> List[Alert]:
        """
        Verifica nuevos casos en PACER (casos federales)
        """
        alerts = []
        
        # Simulación de verificación PACER
        # En implementación real, se conectaría al sistema PACER
        
        # Ejemplo de alerta simulada (2% probabilidad)
        import random
        if random.random() < 0.02:  # 2% chance para demo
            case_types = ["Criminal", "Civil", "Bankruptcy", "Appeals"]
            case_type = random.choice(case_types)
            
            alert = Alert(
                id=f"pacer_{person_name.replace(' ', '_')}_{datetime.now().timestamp()}",
                title=f"Nuevo Caso PACER - {case_type}",
                message=f"Nuevo caso {case_type.lower()} en PACER involucra a {person_name}",
                severity=AlertSeverity.CRITICAL if case_type == "Criminal" else AlertSeverity.WARNING,
                source="pacer",
                target_person=person_name,
                target_id=None,
                created_at=datetime.now(),
                channels=[NotificationChannel.EMAIL, NotificationChannel.WEBHOOK],
                metadata={
                    "case_type": case_type,
                    "court": "U.S. District Court",
                    "case_number": f"{random.randint(10, 99)}:{datetime.now().year}:cv:{random.randint(1000, 9999)}",
                    "filing_date": datetime.now().strftime("%Y-%m-%d")
                }
            )
            alerts.append(alert)
        
        return alerts

    async def _check_state_courts(self, person_name: str, 
                                alert_triggers: List[str]) -> List[Alert]:
        """
        Verifica tribunales estatales (múltiples estados)
        """
        alerts = []
        
        # Simulación de verificación en tribunales estatales
        states = ["California", "Texas", "Florida", "New York", "Illinois"]
        
        import random
        if random.random() < 0.015:  # 1.5% chance para demo
            state = random.choice(states)
            court_types = ["Superior Court", "Circuit Court", "District Court"]
            court_type = random.choice(court_types)
            
            alert = Alert(
                id=f"state_{state.lower()}_{person_name.replace(' ', '_')}_{datetime.now().timestamp()}",
                title=f"Caso en Tribunal Estatal - {state}",
                message=f"Nuevo registro en {court_type} de {state} para {person_name}",
                severity=AlertSeverity.WARNING,
                source=f"state_court_{state.lower()}",
                target_person=person_name,
                target_id=None,
                created_at=datetime.now(),
                channels=[NotificationChannel.EMAIL],
                metadata={
                    "state": state,
                    "court_type": court_type,
                    "case_category": "Civil/Criminal TBD",
                    "record_date": datetime.now().strftime("%Y-%m-%d")
                }
            )
            alerts.append(alert)
        
        return alerts

    async def _process_alert(self, alert: Alert, channels: List[str]):
        """
        Procesa y envía una alerta por los canales especificados
        """
        self.alerts_queue.append(alert)
        
        # Enviar por cada canal configurado
        for channel_name in channels:
            if channel_name == "email":
                await self._send_email_alert(alert)
            elif channel_name == "webhook":
                await self._send_webhook_alert(alert)
            elif channel_name == "sms":
                await self._send_sms_alert(alert)
            elif channel_name == "slack":
                await self._send_slack_alert(alert)

    async def _send_email_alert(self, alert: Alert):
        """
        Envía alerta por email
        """
        try:
            config = self.notification_configs["email"]
            
            if not config["password"]:
                print(f"Email not configured, would send: {alert.title}")
                return
            
            msg = MIMEMultipart()
            msg['From'] = config["from_email"]
            msg['To'] = "admin@tavit.com"
            msg['Subject'] = f"TAVIT Alert [{alert.severity.value.upper()}]: {alert.title}"
            
            body = f"""
            ALERTA AUTOMÁTICA TAVIT
            
            Severidad: {alert.severity.value.upper()}
            Objetivo: {alert.target_person}
            Fuente: {alert.source}
            Fecha: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            
            Mensaje:
            {alert.message}
            
            Metadatos:
            {json.dumps(alert.metadata, indent=2)}
            
            ---
            Sistema de Monitoreo Automático TAVIT
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(config["smtp_server"], config["smtp_port"])
            server.starttls()
            server.login(config["username"], config["password"])
            text = msg.as_string()
            server.sendmail(config["from_email"], "admin@tavit.com", text)
            server.quit()
            
        except Exception as e:
            print(f"Error sending email alert: {e}")

    async def _send_webhook_alert(self, alert: Alert):
        """
        Envía alerta por webhook
        """
        try:
            config = self.notification_configs["webhook"]
            webhook_url = config["default_url"]
            
            if not webhook_url:
                print(f"Webhook not configured, would send: {alert.title}")
                return
            
            payload = {
                "alert_id": alert.id,
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity.value,
                "source": alert.source,
                "target_person": alert.target_person,
                "target_id": alert.target_id,
                "created_at": alert.created_at.isoformat(),
                "metadata": alert.metadata
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=config["timeout"]
                )
                
                if response.status_code != 200:
                    print(f"Webhook failed with status {response.status_code}")
                    
        except Exception as e:
            print(f"Error sending webhook alert: {e}")

    async def _send_sms_alert(self, alert: Alert):
        """
        Envía alerta por SMS (simulado)
        """
        # En implementación real, se integraría con Twilio, AWS SNS, etc.
        print(f"SMS Alert (simulated): {alert.title} - {alert.message}")

    async def _send_slack_alert(self, alert: Alert):
        """
        Envía alerta por Slack (simulado)
        """
        # En implementación real, se integraría con Slack API
        print(f"Slack Alert (simulated): {alert.title}")

    async def send_completion_notification(self, investigation_id: str):
        """
        Envía notificación de investigación completada
        """
        alert = Alert(
            id=f"completion_{investigation_id}_{datetime.now().timestamp()}",
            title="Investigación Completada",
            message=f"La investigación {investigation_id} ha sido completada exitosamente",
            severity=AlertSeverity.INFO,
            source="system",
            target_person="Sistema",
            target_id=investigation_id,
            created_at=datetime.now(),
            channels=[NotificationChannel.EMAIL],
            metadata={"investigation_id": investigation_id}
        )
        
        await self._process_alert(alert, ["email", "webhook"])

    def get_recent_alerts(self, hours: int = 24) -> List[Alert]:
        """
        Obtiene alertas recientes
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alerts_queue 
                if alert.created_at > cutoff_time]

    def stop_monitoring(self, monitor_id: str) -> bool:
        """
        Detiene el monitoreo de una persona
        """
        if monitor_id in self.active_monitors:
            self.active_monitors[monitor_id]["active"] = False
            return True
        return False

# Instancia global del manager de notificaciones
notification_manager = NotificationManager()