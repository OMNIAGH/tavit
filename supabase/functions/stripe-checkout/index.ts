import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

interface SubscriptionRequest {
  companyId: string;
  planType: 'basic' | 'professional' | 'enterprise';
  billingPeriod: 'month' | 'year';
  email: string;
  companyName: string;
}

interface PlanConfig {
  name: string;
  price: number;
  features: string[];
  limits: {
    osintQueries: number;
    aiAnalysis: number;
    cameraFeeds: number;
    users: number;
  };
}

const PLANS: Record<string, Record<string, PlanConfig>> = {
  basic: {
    month: {
      name: "TAVIT Basic Monthly",
      price: 99.00,
      features: [
        "100 OSINT Queries/mes",
        "10 Análisis IA/mes", 
        "5 Feeds de cámaras",
        "Hasta 5 usuarios",
        "Soporte por email"
      ],
      limits: {
        osintQueries: 100,
        aiAnalysis: 10,
        cameraFeeds: 5,
        users: 5
      }
    },
    year: {
      name: "TAVIT Basic Yearly",
      price: 990.00, // 2 meses gratis
      features: [
        "100 OSINT Queries/mes",
        "10 Análisis IA/mes",
        "5 Feeds de cámaras", 
        "Hasta 5 usuarios",
        "Soporte por email",
        "2 meses gratis"
      ],
      limits: {
        osintQueries: 100,
        aiAnalysis: 10,
        cameraFeeds: 5,
        users: 5
      }
    }
  },
  professional: {
    month: {
      name: "TAVIT Professional Monthly",
      price: 299.00,
      features: [
        "1,000 OSINT Queries/mes",
        "100 Análisis IA/mes",
        "20 Feeds de cámaras",
        "Hasta 25 usuarios",
        "Alertas en tiempo real",
        "API access",
        "Soporte prioritario"
      ],
      limits: {
        osintQueries: 1000,
        aiAnalysis: 100,
        cameraFeeds: 20,
        users: 25
      }
    },
    year: {
      name: "TAVIT Professional Yearly", 
      price: 2990.00, // 2 meses gratis
      features: [
        "1,000 OSINT Queries/mes",
        "100 Análisis IA/mes",
        "20 Feeds de cámaras",
        "Hasta 25 usuarios", 
        "Alertas en tiempo real",
        "API access",
        "Soporte prioritario",
        "2 meses gratis"
      ],
      limits: {
        osintQueries: 1000,
        aiAnalysis: 100,
        cameraFeeds: 20,
        users: 25
      }
    }
  },
  enterprise: {
    month: {
      name: "TAVIT Enterprise Monthly",
      price: 999.00,
      features: [
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
      limits: {
        osintQueries: 10000,
        aiAnalysis: -1, // Ilimitado
        cameraFeeds: 50,
        users: -1 // Ilimitado
      }
    },
    year: {
      name: "TAVIT Enterprise Yearly",
      price: 9990.00, // 2 meses gratis
      features: [
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
      limits: {
        osintQueries: 10000,
        aiAnalysis: -1,
        cameraFeeds: 50,
        users: -1
      }
    }
  }
};

serve(async (req) => {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE, PATCH',
    'Access-Control-Max-Age': '86400',
    'Access-Control-Allow-Credentials': 'false'
  };

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const STRIPE_SECRET_KEY = Deno.env.get('STRIPE_SECRET_KEY');
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL');

    if (!STRIPE_SECRET_KEY) {
      throw new Error('STRIPE_SECRET_KEY not configured');
    }

    const requestData = await req.json() as SubscriptionRequest;
    const { companyId, planType, billingPeriod, email, companyName } = requestData;

    // Validar plan
    const planConfig = PLANS[planType]?.[billingPeriod];
    if (!planConfig) {
      throw new Error(`Plan inválido: ${planType}/${billingPeriod}`);
    }

    // Crear customer en Stripe
    const customerResponse = await fetch('https://api.stripe.com/v1/customers', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${STRIPE_SECRET_KEY}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        email: email,
        name: companyName,
        metadata: JSON.stringify({
          companyId: companyId,
          planType: planType,
          billingPeriod: billingPeriod
        })
      })
    });

    if (!customerResponse.ok) {
      const error = await customerResponse.text();
      throw new Error(`Error creando customer: ${error}`);
    }

    const customer = await customerResponse.json();

    // Crear price en Stripe
    const priceResponse = await fetch('https://api.stripe.com/v1/prices', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${STRIPE_SECRET_KEY}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        unit_amount: (planConfig.price * 100).toString(), // Centavos
        currency: 'usd',
        recurring: JSON.stringify({
          interval: billingPeriod === 'year' ? 'year' : 'month'
        }),
        product_data: JSON.stringify({
          name: planConfig.name,
          description: planConfig.features.join(', ')
        }),
        metadata: JSON.stringify({
          planType: planType,
          billingPeriod: billingPeriod
        })
      })
    });

    if (!priceResponse.ok) {
      const error = await priceResponse.text();
      throw new Error(`Error creando price: ${error}`);
    }

    const price = await priceResponse.json();

    // Crear suscripción en Stripe
    const subscriptionResponse = await fetch('https://api.stripe.com/v1/subscriptions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${STRIPE_SECRET_KEY}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        customer: customer.id,
        items: JSON.stringify([{ price: price.id }]),
        payment_behavior: 'default_incomplete',
        payment_settings: JSON.stringify({
          save_default_payment_method: 'on_subscription'
        }),
        expand: JSON.stringify(['latest_invoice.payment_intent'])
      })
    });

    if (!subscriptionResponse.ok) {
      const error = await subscriptionResponse.text();
      throw new Error(`Error creando suscripción: ${error}`);
    }

    const subscription = await subscriptionResponse.json();

    // Actualizar company en Supabase
    if (SUPABASE_SERVICE_ROLE_KEY && SUPABASE_URL) {
      const updateResponse = await fetch(`${SUPABASE_URL}/rest/v1/companies?id=eq.${companyId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
          'Content-Type': 'application/json',
          'apikey': SUPABASE_SERVICE_ROLE_KEY
        },
        body: JSON.stringify({
          stripe_customer_id: customer.id,
          subscription_plan: planType,
          subscription_status: subscription.status,
          updated_at: new Date().toISOString()
        })
      });

      if (updateResponse.ok) {
        // Insertar suscripción en tabla stripe_subscriptions
        await fetch(`${SUPABASE_URL}/rest/v1/stripe_subscriptions`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
            'Content-Type': 'application/json',
            'apikey': SUPABASE_SERVICE_ROLE_KEY
          },
          body: JSON.stringify({
            company_id: companyId,
            stripe_subscription_id: subscription.id,
            plan_name: planConfig.name,
            plan_price: planConfig.price,
            billing_period: billingPeriod,
            status: subscription.status,
            current_period_start: new Date(subscription.current_period_start * 1000).toISOString(),
            current_period_end: new Date(subscription.current_period_end * 1000).toISOString()
          })
        });
      }
    }

    // Retornar datos para el checkout
    const response = {
      subscriptionId: subscription.id,
      customerId: customer.id,
      clientSecret: subscription.latest_invoice.payment_intent.client_secret,
      planConfig: planConfig,
      status: subscription.status
    };

    return new Response(JSON.stringify(response), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Error in stripe-checkout:', error);
    
    const errorResponse = {
      error: {
        code: 'CHECKOUT_ERROR',
        message: error.message || 'Error procesando checkout'
      }
    };

    return new Response(JSON.stringify(errorResponse), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});