"""
TAVIT Platform v3.1 - Model Utils Simplificado
Versión simplificada sin dependencias de CatBoost para demo
"""

import random
import math
from typing import Dict, Any, List

class SimplifiedMLModels:
    """Modelos ML simplificados para demostración"""
    
    def __init__(self):
        self.fraud_model_trained = True
        self.risk_model_trained = True
        
    def predict_fraud(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulación de predicción de fraude con algoritmos de demostración
        """
        # Características para simular predicción
        nombre = features.get('nombre', '')
        documento = features.get('documento', '')
        monto = features.get('monto', 0)
        ubicacion = features.get('ubicacion', '')
        
        # Algoritmo simplificado basado en características
        base_score = 0.2
        
        # Factor por monto (montos altos = mayor riesgo)
        if monto > 100000:
            base_score += 0.3
        elif monto > 50000:
            base_score += 0.2
        elif monto > 10000:
            base_score += 0.1
            
        # Factor por longitud del documento
        if len(documento) < 6 or len(documento) > 12:
            base_score += 0.1
            
        # Factor por ubicación (simulado)
        if 'desconocido' in ubicacion.lower() or 'rural' in ubicacion.lower():
            base_score += 0.15
            
        # Añadir algo de aleatoriedad para simulación
        fraud_probability = min(0.95, max(0.01, base_score + random.uniform(-0.1, 0.1)))
        
        # Determinar confianza
        confidence = 0.85 + random.uniform(-0.1, 0.1)
        
        return {
            "fraud_probability": fraud_probability,
            "fraud_score": int(fraud_probability * 100),
            "confidence": confidence,
            "classification": "ALTO RIESGO" if fraud_probability > 0.5 else "BAJO RIESGO",
            "model_version": "v3.1-simplified",
            "algorithm": "Gradient Boosting Simulation",
            "feature_importance": {
                "monto": 0.35,
                "documento": 0.25,
                "ubicacion": 0.20,
                "nombre": 0.20
            }
        }
    
    def predict_risk_score(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulación de scoring de riesgo
        """
        edad = features.get('edad', 30)
        ingresos = features.get('ingresos_anuales', 50000)
        tipo_poliza = features.get('tipo_poliza', 'vida')
        historial = features.get('historial_credito', 'bueno')
        
        # Algoritmo simplificado
        base_score = 50
        
        # Factor por edad
        if edad < 25:
            base_score += 20
        elif edad > 60:
            base_score += 15
        elif edad < 40:
            base_score -= 10
            
        # Factor por ingresos
        if ingresos < 30000:
            base_score += 25
        elif ingresos > 100000:
            base_score -= 15
            
        # Factor por historial crediticio
        if historial == 'malo':
            base_score += 30
        elif historial == 'regular':
            base_score += 10
        elif historial == 'excelente':
            base_score -= 20
            
        # Factor por tipo de póliza
        if tipo_poliza == 'vida':
            base_score += 5
        elif tipo_poliza == 'salud':
            base_score += 10
        elif tipo_poliza == 'auto':
            base_score -= 5
            
        # Asegurar que esté en rango válido
        risk_score = max(0, min(100, int(base_score)))
        
        # Clasificación
        if risk_score >= 70:
            classification = "ALTO RIESGO"
            premium_adjustment = 1.5
        elif risk_score >= 40:
            classification = "RIESGO MEDIO"
            premium_adjustment = 1.2
        else:
            classification = "BAJO RIESGO"
            premium_adjustment = 0.8
            
        return {
            "risk_score": risk_score,
            "classification": classification,
            "premium_adjustment": premium_adjustment,
            "confidence": 0.88,
            "model_version": "v3.1-simplified",
            "algorithm": "Risk Scoring Simulation",
            "factors": {
                "edad": edad,
                "ingresos": ingresos,
                "historial": historial,
                "tipo_poliza": tipo_poliza
            }
        }

# Instancia global para uso en main.py
ml_models = SimplifiedMLModels()
