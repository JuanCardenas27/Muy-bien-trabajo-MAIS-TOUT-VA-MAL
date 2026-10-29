# ADR-006: Proveedor LLM para la generación de tarjetas

**Estado:** Aceptado (provisional — «por ahora», decisión de Leonardo, 2026-10-29)
**Fecha:** 2026-10-29
**Contexto:** SPK-06 — Elegir proveedor LLM con API compatible con OpenAI
(decisión del usuario, 2026-10-14: API key propia de un proveedor con API
compatible con OpenAI, sin depender de Azure). CRD-04 implementa el cliente
contra este contrato.

## Decisión

- **Proveedor:** Kiosapi — `LLM_BASE_URL = https://kiosapi.com/v1`
- **Modelo:** `LLM_MODEL = glm-5.3-flash-free`
- **Auth:** `Authorization: Bearer <LLM_API_KEY>` (verificado; el header
  alternativo `api-key` no fue necesario).
- **Requisito del cliente:** enviar siempre un `User-Agent` de navegador
  fijo. El gateway está tras Cloudflare y rechaza clientes sin él
  (error 1010). CRD-04 debe fijarlo, como ya hace la configuración de
  opencode de este proyecto.
- **`response_format` con `json_schema` estricto:** soportado y verificado
  contra el esquema mínimo de tarjetas `{cards: [{front_fr, back_es}]}`.

## Evidencia (scripts/spikes/spk06_llm_probe.py, 2026-10-29)

- `GET /models` → HTTP 200; 26 modelos en el catálogo de la key.
- `glm-5.3-flash-free` → HTTP 200 en 12–29 s; el contenido parsea y cumple
  el esquema estricto; `usage` ≈ 750–900 tokens por llamada de prueba (la
  mayor parte, tokens de razonamiento). La latencia obliga a un timeout
  amplio en el cliente.
- `deepseek-v4.1-flash-free` → descartado por ahora: HTTP 520 (error de
  origen de Cloudflare) tras 42 s, en línea con la inestabilidad ya
  observada en esa ruta.

## Costo

- Precio de la ruta elegida: **$0 por 1M de tokens** (entrada y salida)
  mientras dure el nivel gratuito del proveedor.
- Estimación del plan: 30 publicaciones/día × ~4k tokens × 30 días ≈
  3,6M de tokens/mes → **$0/mes** al precio actual.
- Sin SLA: límites de tasa y disponibilidad variables. Si el proveedor no
  está disponible, `cards.llm = "off"` en `frances-data` (degradación
  prevista en el plan maestro).

## Consecuencias

- CRD-04 consume solo las variables `LLM_BASE_URL`, `LLM_API_KEY` y
  `LLM_MODEL`; ningún código debe asumir Kiosapi más allá de este contrato.
- Cambiar de proveedor = cambiar el entorno y re-correr la sonda SPK-06;
  este ADR se actualiza con la nueva evidencia.
