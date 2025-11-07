"""
Chat Interactivo con OpenAI para TAVIT Platform
Sistema de chat inteligente con historial y configuración personalizable
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
import os
from dotenv import load_dotenv
from auth import verify_token

load_dotenv()

router = APIRouter(prefix="/api/v1", tags=["Chat"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# System prompt por defecto
DEFAULT_SYSTEM_PROMPT = """Eres un asistente experto de TAVIT, una plataforma avanzada de verificación de clientes para aseguradoras que utiliza inteligencia artificial con CatBoost y análisis OSINT de 25+ fuentes de datos.

Tu función es ayudar a empresas de seguros a:
- Entender cómo funciona la detección de fraude con IA
- Explicar el sistema de scoring de riesgo
- Interpretar resultados de análisis OSINT
- Responder preguntas sobre compliance y verificación legal
- Explicar cómo CatBoost mejora las predicciones

Características clave de TAVIT:
- Accuracy del 94.7% en detección de fraude
- Predicciones en menos de 2 segundos
- 25+ fuentes de datos OSINT integradas
- Algoritmos de Gradient Boosting con CatBoost
- Análisis predictivo en tiempo real

Sé profesional, técnico pero accesible, y enfócate en el valor empresarial."""

# Historial de conversaciones (en producción usar base de datos)
CHAT_HISTORY = {}

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model: Optional[str] = "gpt-4o-mini"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 800

class ChatConfigUpdate(BaseModel):
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None

# Configuración global del chat
CHAT_CONFIG = {
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "model": "gpt-4o-mini",
    "temperature": 0.7
}

@router.post("/chat")
async def chat_with_ai(request: ChatRequest):
    """
    Chat interactivo con OpenAI GPT-4o-mini
    
    Proporciona respuestas inteligentes sobre TAVIT, análisis OSINT,
    detección de fraude y scoring de riesgo.
    """
    try:
        # Generar o recuperar conversation_id
        conversation_id = request.conversation_id or f"conv_{datetime.now().timestamp()}"
        
        # Recuperar historial
        if conversation_id not in CHAT_HISTORY:
            CHAT_HISTORY[conversation_id] = []
        
        # Agregar mensaje del usuario al historial
        CHAT_HISTORY[conversation_id].append({
            "role": "user",
            "content": request.message
        })
        
        # Preparar mensajes para OpenAI
        messages = [
            {"role": "system", "content": CHAT_CONFIG["system_prompt"]}
        ] + CHAT_HISTORY[conversation_id][-10:]  # Últimos 10 mensajes
        
        # Llamar a OpenAI API
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": request.model or CHAT_CONFIG["model"],
            "messages": messages,
            "temperature": request.temperature or CHAT_CONFIG["temperature"],
            "max_tokens": request.max_tokens
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENAI_API_URL,
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error de OpenAI API: {response.text}"
                )
            
            data = response.json()
            
            # Extraer respuesta
            assistant_message = data["choices"][0]["message"]["content"]
            
            # Agregar respuesta al historial
            CHAT_HISTORY[conversation_id].append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return {
                "conversation_id": conversation_id,
                "message": assistant_message,
                "model_used": data["model"],
                "tokens_used": {
                    "prompt": data["usage"]["prompt_tokens"],
                    "completion": data["usage"]["completion_tokens"],
                    "total": data["usage"]["total_tokens"]
                },
                "timestamp": datetime.now().isoformat()
            }
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout al conectar con OpenAI"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en chat: {str(e)}"
        )

@router.get("/chat/history/{conversation_id}")
async def get_chat_history(conversation_id: str):
    """
    Obtener historial de una conversación
    """
    if conversation_id not in CHAT_HISTORY:
        return {
            "conversation_id": conversation_id,
            "messages": [],
            "total_messages": 0
        }
    
    return {
        "conversation_id": conversation_id,
        "messages": CHAT_HISTORY[conversation_id],
        "total_messages": len(CHAT_HISTORY[conversation_id])
    }

@router.delete("/chat/history/{conversation_id}")
async def clear_chat_history(conversation_id: str):
    """
    Limpiar historial de una conversación
    """
    if conversation_id in CHAT_HISTORY:
        del CHAT_HISTORY[conversation_id]
    
    return {
        "message": "Historial eliminado",
        "conversation_id": conversation_id
    }

@router.get("/chat/config")
async def get_chat_config(token_payload: dict = Depends(verify_token)):
    """
    Obtener configuración actual del chat (solo admin)
    """
    return {
        "config": CHAT_CONFIG,
        "available_models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT
    }

@router.put("/chat/config")
async def update_chat_config(
    config: ChatConfigUpdate,
    token_payload: dict = Depends(verify_token)
):
    """
    Actualizar configuración del chat (solo admin)
    """
    if config.system_prompt:
        CHAT_CONFIG["system_prompt"] = config.system_prompt
    
    if config.model:
        CHAT_CONFIG["model"] = config.model
    
    if config.temperature is not None:
        CHAT_CONFIG["temperature"] = config.temperature
    
    return {
        "message": "Configuración actualizada",
        "new_config": CHAT_CONFIG,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/chat/test")
async def test_chat_connection(token_payload: dict = Depends(verify_token)):
    """
    Probar conexión con OpenAI API (solo admin)
    """
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "Hola, responde OK si puedes leerme"}
            ],
            "max_tokens": 10
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_API_URL,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": "Conexión con OpenAI exitosa",
                    "api_responsive": True
                }
            else:
                return {
                    "status": "error",
                    "message": f"Error: {response.status_code}",
                    "api_responsive": False
                }
                
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "api_responsive": False
        }
