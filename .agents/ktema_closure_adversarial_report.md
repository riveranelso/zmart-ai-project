# CIERRE ADVERSARIAL — FL PROPERTY INTELLIGENCE (KTEMA) — Reporte final

**Repo:** `~/workspace/zmart-ai-project` · **Branch:** `zmart360/omar-core-v1` · **Rango:** `5e36df4..c73acf7`
**Fecha:** 2026-10-04 · **Rol:** zion-adversarial (adversario de ZION)
**Suite:** `python3 -m unittest discover -s tests -p "test_zion_*.py"` → **554 tests, OK** (exit 0)

**Boundaries verificados:** cero imports de red en `ktema.py` (regex + AST sobre imports: solo `dataclasses, hashlib, json, re, datetime, pathlib, typing, .registry`); cero imports del módulo SCAN (`scan_water` ausente); `FetchIntent.target_descriptor` opaco (`fixture://…`, `"http"` rechazado en `_make_fetch_intent` — con una salvedad P2); `PARCEL_PATTERNS == {}`; solo el fixture publicado (`fixture_registry`, registry por defecto vacío).

---

## Estado del catálogo (ataques T1–T5 + lista completa)

| Ataque del catálogo | Estado |
|---|---|
| T1 `test_cache_hit_requires_same_isolation_key` | ✅ CUBIERTO (test + impl) |
| T2 `test_not_found_…` (existence claim) | ✅ CUBIERTO |
| T3 `test_spoofed_business_ids_fail_closed` | ✅ CUBIERTO (exact-match SAN PEDRO) |
| T4 `test_cross_county_zip_is_ambiguous` | ✅ CUBIERTO |
| T5 `test_owner_without_authorization_fails_closed` | ⚠️ PARCIAL — el gate existe en `validate_property_profile`, pero `KtemaCache.put` lo **bypassea** (ver P0) |
| `test_duplicate_isolation_key_fails_closed` | ❌ AUSENTE — ktema no puede detectar colisiones de `isolation_key` en el registry (fuera del código de ktema; integridad de datos del registry) → P2 |
| `test_registry_typo_business_does_not_shadow_canonical` | ❌ AUSENTE — mitigado por exact-match de SAN PEDRO (un typo no registrado falla cerrado), pero si el typo **está registrado**, ktema lo sirve con su propio `isolation_key`; no hay verificación → P2 |
| `test_brand_id_is_not_business_id` | ⚠️ IMPLÍCITO — `sanpedro_resolve` es dict lookup exacto, `"SCAN"`/`"scan"` → `BUSINESS_NOT_REGISTERED` → `KTEMA_BUSINESS_INVALID`; sin test explícito → P2 (gap de test, no de código) |
| `test_parcel_id_validated_per_county_format` | ⚠️ PARCIAL POR DISEÑO — `PARCEL_PATTERNS` vacío ⇒ todo parcel_id → `INCONCLUSIVE`, ningún parcel llega a fuente. Al entrar patrones reales, este test debe existir → P2 |
| `test_coordinates_outside_fl_fail_before_county_lookup` | ⚠️ IMPLÍCITO — coordenadas siempre → `INCONCLUSIVE` (`KTEMA_COORDS_GEOMETRY_NOT_EMBEDDED`), cero lookup; sin test explícito de coords fuera de FL → P2 |
| `test_timeout_fallback_never_serves_stale_as_verified` | ⚠️ PARCIAL — no existe path de timeout-fallback (el router no consulta caché; expirados son miss; `put` preserva timestamps originales). Debilidad real: `get()` no marca staleness ni valida `source_updated_at` → P1 |
| `test_source_record_id_matches_source_pattern` | ❌ EXPUESTO — `normalize` acepta cualquier string no-blanco; `raw_reference` se construye interpolando `record_id` → P1 |
| `test_scan_context_cannot_bleed_into_profile` | ⚠️ IMPLÍCITO — no existe canal de contexto SCAN en el código (`plan_ktema_batch`/`normalize` no reciben `mission_defaults`); test de namespace sin `SCAN_` existe; sin test explícito → P2 |
| `test_address_matching_two_parcels_is_ambiguous` | ⚠️ PARCIAL — address→parcela no existe en ktema (address-only → `INCONCLUSIVE`); ambigüedad a nivel fuente cubierta (`KTEMA_MATCH_AMBIGUOUS` con candidatos) → P2 |
| Resto del catálogo (negative TTL, key separation, status cerrado, freshness, owner empty→None, no-SCAN dispatch, batch business explícito…) | ✅ CUBIERTO |

---

## P0 — bloquea el cierre

### P0-1. `KtemaCache.put` almacena owner PII sin autorización upstream real
- **Invariante violada:** CHERUBIM + T5 — `owner` solo sobrevive validación con `owner_authorized=True`; la decisión de autorización vive en intake/normalize, **fail closed**.
- **PoC (verificado, funciona):**
```python
from zion_core.ktema import KtemaCache, PropertyProfile, PropertyQuery, query_fingerprint, VERIFIED
profile = PropertyProfile(state="FL", county="Orange", parcel_id="P-1", site_address="S",
    zip="32801", source="fixture", source_record_id="PA-1",
    verification_status=VERIFIED, isolation_key="los-duros",
    owner="Jane Doe (PII jamas autorizada)")  # el constructor NO tiene gate
cache = KtemaCache(clock=lambda: "2026-10-04T10:00:00+00:00")
fp = query_fingerprint(PropertyQuery(business_id="los-duros", parcel_id="P-1"))
key = cache.put(isolation_key="los-duros", source_id="fixture",
                query_fingerprint=fp, source_record_id="PA-1", profile=profile)
assert cache.get(key, requesting_isolation_key="los-duros").owner.startswith("Jane Doe")
# PII almacenada y servida como hit legítimo sin que ninguna autorización existiera
```
- **Mecanismo:** `put()` re-valida con `owner_authorized=True` **incondicional**; el docstring lo justifica con "must have been authorized upstream" — confianza por comentario, sin prueba. Cualquier poseedor del handle del caché (componente downstream, bug, caller adversarial) inyecta PII que luego se sirve al tenant legítimo como entrada válida.
- **Fix (1 línea):** en `put()`, llamar `validate_property_profile(profile)` con `owner_authorized=False` (nunca dispensar el gate) y exigir prueba explícita de autorización o `owner=None` antes del `put`.

---

## P1 — debería corregirse

### P1-1. `normalize` no valida `retrieved_at`: TypeError crudo escapa del boundary
- **Invariante:** "malformed adapter response rejected at boundary" + contrato "todo error empieza con `KTEMA_*`".
- **PoC (verificado):** `FixturePropertySource({}).normalize({"source_record_id":"PA-1","source_updated_at":"2026-10-03T12:00:00+00:00","retrieved_at":12345}, q, "los-duros")` → `TypeError: '<' not supported between instances of 'int' and 'str'` (el `retrieved_at` int llega a la comparación lexicográfica de `validate_property_profile`). `source_updated_at` sí se valida; `retrieved_at` no.
- **Fix:** validar `retrieved_at` como ISO en `normalize` igual que `source_updated_at` → `KTEMA_ADAPTER_RESPONSE_MALFORMED`.

### P1-2. El check de time-inversion es comparación lexicográfica: falsos negativos con offsets mixtos
- **Invariante:** `KTEMA_PROVENANCE_TIME_INVERSION` detecta `retrieved_at < source_updated_at`. El comentario asume "single ISO profile" pero nada lo impone.
- **PoC (verificado):** `source_updated_at="2026-10-04T03:30:00-05:00"` (= 08:30 UTC), `retrieved_at="2026-10-04T08:00:00+00:00"` (= 08:00 UTC, **anterior**) → `validate_property_profile` lo **ACEPTA** porque `"08:00:00+00:00" > "03:30:00-05:00"` lexicográficamente.
- **Fix:** parsear ambos con `_parse_iso` y comparar datetimes aware; rechazar si alguno no parsea.

### P1-3. Los campos futuros SCAN (`pwsid`, `water_source`, …) aceptan valores aunque la doc dice "None placeholders only, NOT implemented"
- **Invariante:** "SCAN is NOT implemented here".
- **PoC (verificado):** `PropertyProfile(…, pwsid="FL1234567", water_source="ground")` pasa `validate_property_profile` sin objeción. Un caller puede contrabandear datos SCAN dentro de perfiles ktema sin que nada falle cerrado.
- **Fix:** en `validate_property_profile`, rechazar cualquier campo `water_*`/`pwsid`/`utility`/`service_area`/`well_probability`/`permit_intelligence` no-None con `KTEMA_SCAN_FIELD_UNIMPLEMENTED`.

### P1-4. `raw_reference` se construye interpolando `source_record_id` (contradice su propio docstring)
- **Invariante:** "raw_reference … is NEVER constructed by interpolating PII".
- **Escenario:** `normalize` hace `raw_reference=f"fixture://{FIXTURE_SOURCE_ID}/{record_id}"` donde `record_id` viene del record inyectado (sin validación de patrón — el catálogo pedía `test_source_record_id_matches_source_pattern`, ausente). Si un record trae PII en `source_record_id`, fluye a `raw_reference` y `to_cronicas_event` emite sus primeros 64 chars a CRONICAS. **Truncar ≠ redactar.**
- **Fix:** no interpolar `record_id`; usar el puntero opaco provisto por el caller o `sha256` del record id, y validar `source_record_id` contra el patrón declarado por la fuente.

### P1-5. `get()` sirve perfiles VERIFIED sin marca de staleness; positivos sin validity nunca expiran
- **Invariante del catálogo:** stale se sirve como stale o se rechaza (`test_stale_cache_served_as_stale_or_rejected`).
- **Escenario:** `put` de un perfil VERIFIED con `source_updated_at` de 2020 → `get()` lo devuelve VERIFIED sin `stale=True` ni chequeo de frescura (solo TTL desde el `put`, y con `validity_days={}` los positivos **nunca expiran** — `test_positive_without_configured_validity_never_expires` lo consagra). El TTL acota edad-del-put, no vintage de la fuente.
- **Fix:** `get()` con parámetro opcional de frescura (`max_source_age_days`) que marque `stale=True` o eleve `KTEMA_CACHE_STALE`; documentar que el consumidor debe llamar `is_fresh`.

---

## P2 — endurecimiento futuro / gaps de test

- **P2-1.** `FetchIntent` construible directo bypassa el gate de `target_descriptor` (`"http"` rechazado solo en `_make_fetch_intent`; PoC verificado: `FetchIntent(…, target_descriptor="https://evil.example/payload", …)` se construye OK). Fix: validar en `__post_init__` o constructor privado.
- **P2-2.** `plan_ktema_batch` con `latitude="abc"` eleva `ValueError` crudo (`could not convert string to float`) sin prefijo `KTEMA_*` — `_canonical_query_key._n` hace `float()` sobre input no validado. Fix: validar coordenadas en `_normalize_batch_query` → `KTEMA_COORDS_INVALID` antes del fingerprint.
- **P2-3.** Quirk: un `parcel_id` que contenga `"http"` hace que `fetch_intent` falle con `KTEMA_INTENT_DESCRIPTOR_FORBIDDEN` (el substring check es demasiado ancho). Fix: validar esquema en vez de substring, o escapar.
- **P2-4.** Gaps de test sin gap de código (recomendado añadir): `test_brand_id_is_not_business_id` (`"SCAN"`/`"scan"`), `test_coordinates_outside_fl_fail_before_county_lookup` (Georgia/Golfo), `test_scan_context_cannot_bleed_into_profile`, `test_registry_typo_business_does_not_shadow_canonical`.
- **P2-5.** `test_duplicate_isolation_key_fails_closed`: ktema no puede detectarlo (es integridad de datos del registry SAN PEDRO); escalar a validación del registry, fuera de esta capability.
- **P2-6.** `test_parcel_id_validated_per_county_format`: bloqueado por diseño hasta que `PARCEL_PATTERNS` deje de estar vacío; al poblarlo, el test debe entrar con el patrón.
- **P2-7.** `zmart360/MODULE_REGISTRY.md` dice "Increments 1-4 complete" — drift de docs tras el Increment 5.
- **P2-8.** `load_county_table` con counties duplicados en distinto orden: OK (ordena + rechaza duplicados intra-ZIP). Sin hallazgo.

## Veredicto

**Hay 1 P0 → la capability NO debe cerrarse hasta corregirlo** (`KtemaCache.put` dispensa el owner gate por fiat; PoC funcional arriba). Los 5 P1 son debilidades reales con PoC/escenario verificado. Todo lo demás del catálogo está cubierto o mitigado por diseño documentado.
