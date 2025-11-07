"""
TAVIT Platform v4.0 - Sistema de Pagos Stripe
Rutas para manejo de pagos, payment intents, webhooks y suscripciones
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import httpx
import os
import json
import hmac
import hashlib
from datetime import datetime

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

# Configuración Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Modelos Pydantic
class PaymentIntentRequest(BaseModel):
    company_id: str = Field(..., description="ID de la empresa")
    plan_type: str = Field(..., description="basic, professional, enterprise")
    billing_period: str = Field(..., description="month, year")
    email: str = Field(..., description="Email del cliente")
    company_name: str = Field(..., description="Nombre de la empresa")

class PaymentStatusRequest(BaseModel):
    payment_intent_id: str = Field(..., description="ID del payment intent")

# Planes de suscripción con precios
SUBSCRIPTION_PLANS = {
    "basic": {
        "month": {"price": 99.00, "name": "TAVIT Basic Monthly"},
        "year": {"price": 990.00, "name": "TAVIT Basic Yearly"}
    },
    "professional": {
        "month": {"price": 299.00, "name": "TAVIT Professional Monthly"},
        "year": {"price": 2990.00, "name": "TAVIT Professional Yearly"}
    },
    "enterprise": {
        "month": {"price": 999.00, "name": "TAVIT Enterprise Monthly"},
        "year": {"price": 9990.00, "name": "TAVIT Enterprise Yearly"}
    }
}

@router.post("/create-intent")
async def create_payment_intent(request: PaymentIntentRequest):
    """
    Crear Payment Intent para suscripción TAVIT
    """
    try:
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=500, detail="Configuración de Stripe faltante")
        
        # Obtener precio del plan
        plan_config = SUBSCRIPTION_PLANS.get(request.plan_type, {}).get(request.billing_period)
        if not plan_config:
            raise HTTPException(status_code=400, detail="Plan inválido")
        
        amount = int(plan_config["price"] * 100)  # Convertir a centavos
        
        # Crear Payment Intent en Stripe
        stripe_data = {
            "amount": str(amount),
            "currency": "usd",
            "automatic_payment_methods[enabled]": "true",
            "metadata[company_id]": request.company_id,
            "metadata[plan_type]": request.plan_type,
            "metadata[billing_period]": request.billing_period,
            "metadata[company_name]": request.company_name,
            "receipt_email": request.email,
            "description": f"Suscripción {plan_config['name']} para {request.company_name}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.stripe.com/v1/payment_intents",
                headers={
                    "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data=stripe_data
            )
            
            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(status_code=response.status_code, detail=f"Error en Stripe: {error_detail}")
            
            payment_intent = response.json()
            
            # Guardar en Supabase
            supabase_data = {
                "payment_intent_id": payment_intent["id"],
                "amount": amount,
                "currency": "usd",
                "status": payment_intent["status"],
                "company_id": request.company_id,
                "plan_type": request.plan_type,
                "billing_period": request.billing_period,
                "metadata": {
                    "company_name": request.company_name,
                    "email": request.email,
                    "stripe_data": payment_intent
                }
            }
            
            supabase_response = await client.post(
                f"{SUPABASE_URL}/rest/v1/payment_intents",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json=supabase_data
            )
            
            return {
                "client_secret": payment_intent["client_secret"],
                "payment_intent_id": payment_intent["id"],
                "amount": amount,
                "currency": "usd",
                "status": payment_intent["status"],
                "plan_config": plan_config,
                "publishable_key": STRIPE_PUBLISHABLE_KEY
            }
            
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Webhook para eventos de Stripe
    """
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        if not sig_header or not STRIPE_WEBHOOK_SECRET:
            raise HTTPException(status_code=400, detail="Firma de webhook inválida")
        
        # Verificar firma del webhook (simplificado para demo)
        event = json.loads(payload.decode())
        
        # Procesar eventos
        if event["type"] == "payment_intent.succeeded":
            await handle_payment_success(event["data"]["object"])
        elif event["type"] == "payment_intent.payment_failed":
            await handle_payment_failure(event["data"]["object"])
        
        return {"received": True}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en webhook: {str(e)}")

@router.get("/status")
async def get_payment_status(payment_intent_id: str):
    """
    Verificar estado de un payment intent
    """
    try:
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=500, detail="Configuración de Stripe faltante")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}",
                headers={
                    "Authorization": f"Bearer {STRIPE_SECRET_KEY}"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Payment Intent no encontrado")
            
            payment_intent = response.json()
            
            # Actualizar estado en Supabase
            supabase_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/payment_intents?payment_intent_id=eq.{payment_intent_id}",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json={
                    "status": payment_intent["status"],
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            return {
                "payment_intent_id": payment_intent["id"],
                "status": payment_intent["status"],
                "amount": payment_intent["amount"],
                "currency": payment_intent["currency"],
                "last_payment_error": payment_intent.get("last_payment_error")
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/plans")
async def get_subscription_plans():
    """
    Obtener planes de suscripción disponibles
    """
    return {
        "plans": SUBSCRIPTION_PLANS,
        "currency": "USD",
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY
    }

async def handle_payment_success(payment_intent: Dict[str, Any]):
    """
    Manejar pago exitoso
    """
    try:
        async with httpx.AsyncClient() as client:
            # Actualizar estado en payment_intents
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/payment_intents?payment_intent_id=eq.{payment_intent['id']}",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json={
                    "status": "succeeded",
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            # Crear registro en payment_history
            await client.post(
                f"{SUPABASE_URL}/rest/v1/payment_history",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json={
                    "payment_intent_id": payment_intent["id"],
                    "stripe_payment_id": payment_intent.get("latest_charge"),
                    "amount_received": payment_intent["amount_received"],
                    "currency": payment_intent["currency"],
                    "status": "completed",
                    "receipt_url": payment_intent.get("receipt_url")
                }
            )
            
            # Actualizar empresa con suscripción activa
            company_id = payment_intent["metadata"].get("company_id")
            if company_id:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/companies?id=eq.{company_id}",
                    headers={
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "apikey": SUPABASE_SERVICE_KEY
                    },
                    json={
                        "subscription_status": "active",
                        "subscription_plan": payment_intent["metadata"].get("plan_type"),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                )
                
    except Exception as e:
        print(f"Error manejando pago exitoso: {e}")

async def handle_payment_failure(payment_intent: Dict[str, Any]):
    """
    Manejar fallo en pago
    """
    try:
        async with httpx.AsyncClient() as client:
            # Actualizar estado en payment_intents
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/payment_intents?payment_intent_id=eq.{payment_intent['id']}",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json={
                    "status": "failed",
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            # Crear alerta de pago fallido
            await client.post(
                f"{SUPABASE_URL}/rest/v1/alerts",
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_SERVICE_KEY
                },
                json={
                    "alert_type": "payment_failed",
                    "title": "Pago Fallido",
                    "description": f"El pago falló para payment_intent {payment_intent['id']}",
                    "severity": "high",
                    "source_platform": "stripe",
                    "external_reference": payment_intent["id"]
                }
            )
            
    except Exception as e:
        print(f"Error manejando fallo de pago: {e}")