# ADR-004: Tabla canónica de etiquetas de fonemas (fr-FR)

**Estado:** Aceptado
**Fecha:** 2026-10-18
**Contexto:** SPK-04 — fixtures reales de Azure Pronunciation Assessment

## Decisión

La etiqueta canónica de fonema es **IPA en forma normalizada NFC**. Esta tabla es la
única fuente de verdad para etiquetas de fonemas en todo el sistema (R-11):

- `src/frances/cards/phoneme_map.py` (`ESPEAK_TO_AZURE`, CRD-06): mapea la salida
  de `espeak-ng -v fr-fr --ipa` a la etiqueta canónica.
- `web/src/pron/phonemeLabels.ts` (`PHONEME_LABELS`, `normalizePhoneme`, PRN-01):
  normaliza la etiqueta cruda que devuelve Azure a la misma etiqueta canónica.

El nombre «AZURE» en `ESPEAK_TO_AZURE` queda por historia; el valor es siempre la
etiqueta canónica IPA en NFC, no un código propietario de Azure.

## Tabla de etiquetas canónicas (fr-FR)

### Vocales orales (12)

| Etiqueta canónica | Ejemplo |
|---|---|
| a | patte |
| ɑ | pâte |
| e | blé |
| ɛ | lait |
| i | vie |
| o | beau |
| ɔ | porte |
| u | vous |
| y | rue |
| ø | deux |
| œ | cœur |
| ə | le |

### Vocales nasales (4)

| Etiqueta canónica | Ejemplo |
|---|---|
| ɑ̃ | vent |
| ɔ̃ | vont |
| ɛ̃ | vin |
| œ̃ | brun |

### Consonantes (18)

| Etiqueta canónica | Ejemplo |
|---|---|
| p | pain |
| b | bon |
| t | tout |
| d | dans |
| k | café |
| ɡ | gare |
| f | feu |
| v | vous |
| s | soleil |
| z | zéro |
| ʃ | chat |
| ʒ | je |
| m | mère |
| n | non |
| ɲ | montagne |
| ŋ | parking |
| l | lait |
| ʁ | rouge |

### Semivocales (3)

| Etiqueta canónica | Ejemplo |
|---|---|
| j | fille |
| w | oui |
| ɥ | huit |

**Total: 37 fonemas.**

## Notas sobre los fixtures de SPK-04

Los 7 fixtures en `tests/fixtures/azure/` se generaron con audio sintético
(Azure TTS, voz `fr-FR-DeniseNeural`) evaluado por el Pronunciation Assessment
real de Azure. Limitación conocida: Azure no devuelve los símbolos de fonema
(campo `Phoneme` vacío) cuando el audio de entrada es sintético; sí devuelve
scores reales por palabra, sílaba y fonema (AccuracyScore), ErrorType y la
estructura completa del JSON. Los fixtures son válidos para probar el parser
(PRN-01); las etiquetas de fonema se validan contra esta tabla, no contra los
fixtures.

## Referencias

- Fixtures: `tests/fixtures/azure/{bonjour,beau,enfants,rendezvous,restaurant,vin,miscue_marche}.json`
- Consumidores: CRD-06 (`phoneme_map.py`), PRN-01 (`phonemeLabels.ts`), CRD-07 (DrillDecks)
