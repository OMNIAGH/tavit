import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, stripe-signature',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Max-Age': '86400',
    'Access-Control-Allow-Credentials': 'false'
  };

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  try {
    const STRIPE_WEBHOOK_SECRET = Deno.env.get('STRIPE_WEBHOOK_SECRET');
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL');

    if (!STRIPE_WEBHOOK_SECRET || !SUPABASE_SERVICE_ROLE_KEY || !SUPABASE_URL) {
      throw new Error('Missing required environment variables');
    }

    const body = await req.text();
    const signature = req.headers.get('stripe-signature');

    if (!signature) {
      throw new Error('Missing Stripe signature');
    }

    // Verificar webhook signature (simplificado)
    // En producción, usar la librería de Stripe para verificación completa
    const event = JSON.parse(body);

    console.log('Webhook event type:', event.type);
    console.log('Webhook event data:', event.data);

    switch (event.type) {
      case 'customer.subscription.created':
      case 'customer.subscription.updated':
        await handleSubscriptionUpdate(event.data.object, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
        break;

      case 'customer.subscription.deleted':
        await handleSubscriptionCancelled(event.data.object, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
        break;

      case 'invoice.payment_succeeded':
        await handlePaymentSucceeded(event.data.object, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
        break;

      case 'invoice.payment_failed':
        await handlePaymentFailed(event.data.object, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
        break;

      default:
        console.log(`Unhandled event type: ${event.type}`);
    }

    return new Response(JSON.stringify({ received: true }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (error) {
    console.error('Webhook error:', error);
    
    return new Response(JSON.stringify({ 
      error: error.message 
    }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});

async function handleSubscriptionUpdate(subscription: any, supabaseUrl: string, serviceRoleKey: string) {
  try {
    // Obtener customer de Stripe para encontrar company_id
    const customerId = subscription.customer;
    
    // Actualizar estado de suscripción en companies
    const updateCompanyResponse = await fetch(`${supabaseUrl}/rest/v1/companies?stripe_customer_id=eq.${customerId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        subscription_status: subscription.status,
        updated_at: new Date().toISOString()
      })
    });

    if (!updateCompanyResponse.ok) {
      console.error('Failed to update company subscription status');
    }

    // Actualizar o insertar en stripe_subscriptions
    const upsertSubscriptionResponse = await fetch(`${supabaseUrl}/rest/v1/stripe_subscriptions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey,
        'Prefer': 'resolution=merge-duplicates'
      },
      body: JSON.stringify({
        stripe_subscription_id: subscription.id,
        status: subscription.status,
        current_period_start: new Date(subscription.current_period_start * 1000).toISOString(),
        current_period_end: new Date(subscription.current_period_end * 1000).toISOString(),
        cancel_at_period_end: subscription.cancel_at_period_end,
        updated_at: new Date().toISOString()
      })
    });

    if (!upsertSubscriptionResponse.ok) {
      console.error('Failed to update subscription record');
    }

    console.log('Subscription updated successfully');

  } catch (error) {
    console.error('Error handling subscription update:', error);
    throw error;
  }
}

async function handleSubscriptionCancelled(subscription: any, supabaseUrl: string, serviceRoleKey: string) {
  try {
    const customerId = subscription.customer;

    // Marcar empresa como cancelada
    const updateResponse = await fetch(`${supabaseUrl}/rest/v1/companies?stripe_customer_id=eq.${customerId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        subscription_status: 'cancelled',
        updated_at: new Date().toISOString()
      })
    });

    if (!updateResponse.ok) {
      console.error('Failed to update company to cancelled status');
    }

    // Actualizar registro de suscripción
    const updateSubscriptionResponse = await fetch(`${supabaseUrl}/rest/v1/stripe_subscriptions?stripe_subscription_id=eq.${subscription.id}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        status: 'cancelled',
        updated_at: new Date().toISOString()
      })
    });

    if (!updateSubscriptionResponse.ok) {
      console.error('Failed to update subscription record to cancelled');
    }

    console.log('Subscription cancelled successfully');

  } catch (error) {
    console.error('Error handling subscription cancellation:', error);
    throw error;
  }
}

async function handlePaymentSucceeded(invoice: any, supabaseUrl: string, serviceRoleKey: string) {
  try {
    const customerId = invoice.customer;
    const subscriptionId = invoice.subscription;

    // Actualizar estado a activo si el pago fue exitoso
    const updateResponse = await fetch(`${supabaseUrl}/rest/v1/companies?stripe_customer_id=eq.${customerId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        subscription_status: 'active',
        updated_at: new Date().toISOString()
      })
    });

    if (!updateResponse.ok) {
      console.error('Failed to update company to active status after payment');
    }

    // Registrar el pago exitoso
    console.log(`Payment succeeded for customer ${customerId}, subscription ${subscriptionId}`);

  } catch (error) {
    console.error('Error handling payment succeeded:', error);
    throw error;
  }
}

async function handlePaymentFailed(invoice: any, supabaseUrl: string, serviceRoleKey: string) {
  try {
    const customerId = invoice.customer;

    // Marcar como past_due
    const updateResponse = await fetch(`${supabaseUrl}/rest/v1/companies?stripe_customer_id=eq.${customerId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        subscription_status: 'past_due',
        updated_at: new Date().toISOString()
      })
    });

    if (!updateResponse.ok) {
      console.error('Failed to update company to past_due status');
    }

    // Crear alerta de pago fallido
    const alertResponse = await fetch(`${supabaseUrl}/rest/v1/alerts`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${serviceRoleKey}`,
        'Content-Type': 'application/json',
        'apikey': serviceRoleKey
      },
      body: JSON.stringify({
        alert_type: 'payment_failed',
        title: 'Pago Fallido',
        description: 'El pago de la suscripción ha fallado. Por favor actualice su método de pago.',
        severity: 'high',
        source_platform: 'stripe',
        external_reference: invoice.id,
        metadata: {
          invoice_id: invoice.id,
          amount: invoice.amount_due,
          currency: invoice.currency
        }
      })
    });

    console.log(`Payment failed for customer ${customerId}`);

  } catch (error) {
    console.error('Error handling payment failed:', error);
    throw error;
  }
}