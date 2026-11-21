ZION + OMAR — INFORME DE OPTIMIZACIÓN
Fecha: 2026-11-21 · Rama de trabajo: fix/zion-omar-integration-20261121 (aislada, desde zmart360/omar-core-v1)

1. CORREGIDO: cambios realizados y commits.
- Bridge Brain→Omar, hallazgos adversariales 1–9 corregidos (REGLA #2: cada uno con su prueba fallando antes y pasando después; línea base 12/12 en rojo → 11/12 verde):
  - `43cd73e` fix(brain-omar-bridge): errores tipados para config inválida y entradas de tipo incorrecto (hallazgos #6–#9: OmarConfigError, BrainContractError, UnknownBusinessError en vez de excepciones crudas).
  - `2190d49` fix(brain-omar-bridge-service): errores JSON para solicitudes malformadas (hallazgos #2–#5: Content-Length negativo → 400, JSON profundo → 400, métodos no soportados → 405 JSON).
  - `aedef12` fix(brain-omar-bridge-service): autenticación del llamante en POST /bridge/route (hallazgo #1, CRÍTICO): header `X-Bridge-Key` comparado en tiempo constante contra el secreto de entorno `BRIDGE_CALLER_KEY`; sin credencial válida o sin secreto configurado → 401 y Omar nunca es llamado (fail closed). Documentado en el README del servicio.
- PR #2 (fix/omar-zion-brand-memory-20261121): CI verificado ANTES de integrar — 2 check runs "test", ambos `success` (2026-11-21 22:20 UTC). PR sigue abierto y en borrador; no se fusionó nada.
- Sin cambios de arquitectura nueva: se reutilizaron SAN PEDRO, BIBLIA, el bridge existente y la cola de aprobación existente.

2. PRUEBAS: cuántas pasaron y cuáles fallaron.
- Suite completa del repo (rama aislada, tras las correcciones): **928 pasadas, 1 fallida, 212 subtests pasados** (23.4 s; excluido solo test_brain_omar_bridge_live.py, que requiere red y el secreto real).
- La única fallida: `test_unknown_business_id_is_400` — es el hallazgo #10, dejado abierto a propósito (ver PENDIENTES). Desde la corrección del #1, esa prueba recibe 401 (no envía credencial de llamante) antes de llegar a la lógica 422/400.
- Batería obligatoria A–J (evidencia por archivo de prueba):
  - A. OMAR obtiene la memoria correcta de ZION — PASS (test_zion_biblia_precedence 8/8; rutas en vivo 200×4 con el contexto de cada negocio).
  - B. LOS DUROS recupera sus reglas y la referencia al logo oficial — PASS (test_los_duros_canonical_doc_is_retrievable; BIBLIA/LOS_DUROS.md §283: logo = LOCKED ASSET, nunca redibujar).
  - C. Otros negocios NO reciben memoria privada de LOS DUROS — PASS (test_zion_cross_business_candidate_injection 2/2; test_zion_business_isolation_retries 1/1).
  - D. Corrección aprobada sobrevive a un reinicio — PASS (test_zion_correction_memory_crash_recovery 2/2; test_zion_closed_learning_loop 1/1).
  - E. Ningún agente publica sin aprobación — PASS (test_zion_approval_queue 30/30; test_zion_gates 11/11).
  - F. Identificadores antiguos vía alias autorizados — PASS (test_zion_compatibility_contract 3/3; alias `zmart`→`zmart-consumer` del bridge y `zerolag`→`zero-lag-wifi` de SAN PEDRO en la suite).
  - G. Reintentos no duplican operaciones — PASS (test_zion_dedupe 9/9; aislamiento/reintentos 1/1).
  - H. Solicitudes no autorizadas rechazadas — PASS (adversarial de auth del bridge verde tras el #1; en vivo: sin key → 401, negocio desconocido → 400).
  - I. Respaldos restaurables y verificables — PASS (test_zion_durability 4/4; carpeta Drive «Respaldo — Memoria de Yek1» existe, respaldo más reciente 2026-11-20).
  - J. Suite anterior sigue pasando — PASS (928/929; único fallo = #10 intencional).

3. INTEGRACIONES: cuáles funcionan y cuáles siguen pendientes.
- FUNCIONAN (verificado en vivo): Omar Core en Fly (health 200; POST /omar/route 200 para zmart-consumer, scan, zerolag, los-duros; desconocido 400; sin key 401). n8n «NELSON AI | Zmart Brain v1» Active con los 2 nodos sombra del bridge (solo lectura; no se tocó). GitHub (PR #2 CI verde). Google Drive (respaldo diario presente). Obsidian = espejo de solo lectura de BIBLIA.
- PENDIENTES: el servicio del bridge corregido NO está desplegado (sin autorización de despliegue); la app `brain-omar-bridge` no existe en Fly (el token no puede crear apps — UNAUTHORIZED, bloqueo ya conocido). Al desplegarse, la rama sombra de n8n necesitará el header `X-Bridge-Key` y el secreto `BRIDGE_CALLER_KEY` creado en Fly, o recibirá 401.

4. MEMORIA: versión actual y aislamiento confirmado.
- Fuente canónica única: `zmart360/BIBLIA/` en el repo (último commit que la tocó: `1f2665a`, 2026-11-09). El espejo de Obsidian es snapshot fiel de ese commit (7/9 archivos byte-idénticos sin frontmatter; 2 difieren solo en estilo de enlaces).
- Desfase real: el working tree trae cambios de BIBLIA sin commitear (CHANGELOG +1, LOS_DUROS +21, NELSON_DATOS_VERIFICADOS +12/−3) que NO están en Obsidian ni en ningún commit — quedan como trabajo pendiente de commitear por su autor; esta misión no los tocó.
- Aislamiento confirmado por pruebas (C) y en vivo: cada ruta de Omar devuelve solo el contexto de su negocio; el contexto comercial de LOS DUROS (Filadelfia, paquetes, Ellio) no aparece en scan, zerolag ni zmart-consumer. Los paquetes oficiales existen en UN solo lugar del repo: BIBLIA/LOS_DUROS.md (PROMO $125 / MEDIANO $300 / MENSUAL $600 / KIKEO $300); comercial con Blaze: $500 = línea roja/mínimo, Ellio puede subirlo.
- Hallazgo estructural (no corregido, requiere decisión): existen TRES vocabularios de IDs de negocio — SAN PEDRO (`zmart-consumer-rights`, `scan-water-intelligence`, `zero-lag-wifi`, `los-duros`, `yek-family`), bridge/Omar (`zmart-consumer`, `scan`, `zerolag`, `los-duros`) — unidos por dos mapas manuales (registry.py y bridge.py). Añadir un negocio exige tocar ≥3 sitios. Además `omar_core/` está vacío en este repo: el servidor Omar Core que corre en Fly vive fuera del repo; `zion_core/omar.py` es orquestación de misiones, no ese servidor.

5. AGENTES: Blaze, Jessica y demás; estado verificado.
- Blaze Clone (LOS DUROS): existe en el repo (`zion_core/glossolalia.py`); opera solo sobre los-duros y su publicación pasa por la cola de aprobación humana durable (approval_queue, 30/30 pruebas; tenant fijado por business_id). Sin aprobación no publica — verificado por pruebas (E).
- Jessica (recepcionista ZMART AI): NO tiene definición ni código en este repo — aparece solo mencionada en BIBLIA (BRANDS.md, SAN_PEDRO.md, NELSON_DATOS_VERIFICADOS.md). Vive fuera del repo (HighLevel/n8n); no se pudo validar su runtime desde aquí y no se inventó evidencia.
- Agentes de desarrollo del repo (.github/agents/): zion-architect, zion-builder, zion-reviewer, zion-adversarial — presentes y alineados con el loop constructor/revisor (REGLA #2).
- No se creó ningún agente nuevo.

6. PRODUCCIÓN: confirmar que permanece intacta.
- Confirmado: cero despliegues, cero fusiones (main == origin/main en `552cfed`, sin cambios), cero envíos, cero pagos. Fly solo recibió lecturas y probes de ruta autorizados (la máquina de omar-core pasó de stopped a started por autostart al recibir el health check — comportamiento normal de autostop, sin cambios de configuración). n8n solo lectura. zmart-intake no se tocó. Todo el código nuevo vive en commits locales de la rama aislada.

7. PENDIENTES: únicamente bloqueos reales.
- DECISIÓN DE NELSON (hallazgo #10): negocio desconocido en el bridge — ¿400 (contrato entregado y Omar Core en vivo) o 422 (elección documentada del servicio)? El código queda en 422 hasta que Nelson decida; 1 prueba queda en rojo por eso.
- DESPLIEGUE DEL BRIDGE: bloqueado por (a) falta de autorización de despliegue, (b) la app de Fly no existe y el token no puede crearla (Nelson debe crearla desde su sesión), (c) al desplegar hay que crear el secreto `BRIDGE_CALLER_KEY` en Fly y configurar el header en el nodo sombra de n8n.
- ESTADO FLY: la org Mistel Fu reporta `omar-core` como `suspended` (autostop) — responde por autostart, pero el estado declarado no es «deployed»; y `zmart-intake` no aparece bajo esa org según el API consultado. Verificación de cuenta pendiente de Nelson (posible segunda cuenta ya conocida: riveranelso@ vs mistel-fu).
- MEMORIA SIN COMMITEAR: los cambios de BIBLIA en el working tree (LOS_DUROS +21 líneas, etc.) deben commitearse y luego reconstruirse el espejo de Obsidian para cerrar el desfase.
- CONFLICTO DE REGISTRO EN VIVO: la ruta `zerolag` de Omar Core devuelve `asset_status: CONFLICT_REQUIRES_RESOLUTION` (el registro central afirma un asset aprobado; el repo ZeroLag dice que no hay assets oficiales verificados). Requiere resolución de Nelson.
- IDs DE NEGOCIO TRIPLES: unificar SAN PEDRO ↔ bridge/Omar es trabajo de arquitectura con decisión de Nelson (rompe identificadores si se hace mal); no se tocó por la regla de conservar identificadores.
