# HANDOFF.md - Generador de Presupuestos (Acometidas Europa / Grupo Europa)

> Puente de contexto para retomar este proyecto en otra sesion/ordenador.
> Fecha de este handoff: 2026-09-13. Ultimo commit: `5f09df8` (rama `principal`, sincronizada con `origin/principal`, working tree limpio).

## 1. Estado actual

- App Flask funcional en local (`python app.py`, puerto 5000) y con despliegue configurado en **Railway** (`Dockerfile` + `railway.toml`, healthcheck en `/`).
- `app.py` (3491 lineas) es el punto de entrada real y concentra ~35 rutas. `main.py` es un CLI antiguo (Rich/prompt interactivo) que usa una plantilla `MODELO_MAESTRO.docx` que **ya no existe** en `templates/` (fue sustituida por los 15+ modelos especificos) -> `main.py` esta obsoleto/roto, no usarlo como referencia de flujo actual.
- Funcionalidades activas mas alla de lo documentado en `CLAUDE.md`:
  - Generador de presupuestos (15 tipos de documento DOCX).
  - Analizador CCTV multi-video + croquis (`/api/analizar`, async con `job_id` y `/api/analizar_status/<job_id>`).
  - **Editor de croquis/planos con IA** (`/croquis`, `/api/generar_plano_ia`, `/api/generar_planos_multiples` + status por job_id, `/api/regenerar_plano_svg`) - no estaba documentado en CLAUDE.md del proyecto.
  - Chat de correccion de informes por IA (`/api/chat_informe`).
  - Importacion de informes/presupuestos/subcontratas ya generados (`/api/importar_informe`, `/api/importar_presupuesto`, `/api/importar_presupuesto_completo`, `/api/importar_subcontrata`, `/api/extraer_datos_subcontrata`).
  - Aplicar modificaciones a partidas via IA (`/api/aplicar_modificaciones_ia`).
  - Gestion de subcontratas (`/api/subcontratas` GET/POST/DELETE) persistida en `config/subcontratas.json`.
  - Compartir informes publicamente por token (`/api/compartir_informe`, `/ver/<token>`, plantilla `ver_publico.html`).
  - Pagina de configuracion (`/configuracion`, `configuracion.html`) respaldada por `config/app_config.json` (via `utils/app_config.py`).
  - `utils/base_datos.py` + `config/enlaces.db` (SQLite) para algo de persistencia (revisar contenido exacto antes de asumir su esquema).
  - `utils/sheets_registro.py` (212 lineas) integra Google Sheets para registro de presupuestos (numeracion), usando `config/google_credentials.json`.
  - `utils/output_saver.py` gestiona guardado de salidas (posible doble destino local + red, dado el script de auditoria).
  - Script `scripts/auditar_numeracion.py` (+ `.bat`) compara numeracion de presupuestos generados vs carpeta de red -> auditoria diaria de consistencia.
- Ultimos commits relevantes (mas reciente primero):
  - `5f09df8` fix: preservar Total c/IVA en tabla de partidas adicionales de servicios.
  - `03eb8ec` feat: iconos premium (Bootstrap Icons) por tipo de documento.
  - `b0d75f4` chore: recuperar backups sueltos + ampliar `.gitignore`.
  - `0173c28` fix: precios en blanco en partidas multioficio + aviso falso de API key sin configurar.
  - `2fc7286` feat: script de auditoria diaria de numeracion vs carpeta de red.
  - `f08d282` fix: mapeo `fuga_agua` -> plantilla FONTANERIA + checkbox para excluir partidas del servicio.
  - Commits anteriores: mucho trabajo en el editor de croquis/plano (capas, pincel de borrado, distincion anotacion manual vs impresa, limite 413 de Werkzeug al generar PDF con plano de fondo, deteccion de multi-archivo).

## 2. Arquitectura / Stack

- **Backend**: Flask (Python 3.12), `app.py` como monolito de rutas. `debug=True, use_reloader=False` -> **cualquier cambio en `.py` requiere reinicio manual del servidor**.
- **Generacion de documentos**: `python-docx` (`core/docx_generator.py`, `DocxGenerator`, placeholders `[[...]]` que pueden venir partidos en runs XML, ver `_merge_runs`). Tambien `core/excel_generator.py` (uso secundario), `core/html_generator.py` (206 lineas, probablemente para `ver_publico.html` o informes web) y `core/pdf_converter.py` (103 lineas, conversion DOCX/plano -> PDF).
- **IA**: `core/ai_analyst.py` (2862 lineas, el modulo mas grande del repo) - analisis CCTV multimodal, generacion de partidas de obra, chat de correccion de informes, generacion de planos/croquis IA. Modelo: `claude-sonnet-4-6` via SDK `anthropic`. API key en env o en campo UI (`f_apikey`).
- **Video/imagen**: `ffmpeg` en `C:\Users\Usuario\AppData\Local\ffmpeg\bin\ffmpeg.exe` para extraer frames (max 8 por video).
- **Tarifas**: `utils/tarifa_loader.py`, lee `tarifas/TARIFAS.xlsx` (busqueda exacta por codigo y fuzzy por descripcion), columna de precio 4 con fallback a 3, formato ES (coma decimal). Tambien existe `tarifas/BASE_DATOS.xlsx` (revisar su rol, no documentado).
- **Persistencia**: sin base de datos relacional clasica; combinacion de:
  - Archivos DOCX/PDF en `salidas/` (carpeta por presupuesto/informe).
  - `config/enlaces.db` (SQLite, via `utils/base_datos.py`) - posiblemente para tokens de `/ver/<token>` o enlaces compartidos.
  - `config/app_config.json`, `config/subcontratas.json` (JSON planos).
  - Google Sheets para numeracion/registro (`utils/sheets_registro.py`, requiere `google_credentials.json`, `SHEET_ID` configurado en commit `8202900`).
- **Frontend**: Jinja2 + HTML/JS vanilla, sin build step. Paginas clave: `index.html` (generador, UI "chat-step"), `analizar.html` (analizador CCTV), `croquis.html` (editor de planos/croquis con capas y herramientas manuales + IA), `configuracion.html`, `ver_publico.html`, `resultado.html`.
- **Despliegue**: Dockerfile + Railway (`railway.toml`), ademas de uso local via `.bat` (`INICIAR_APP.bat`, `LANZAR_PRESUPUESTOS.bat`, `PUBLICAR_EN_RAILWAY.bat`).
- **Uploads**: `uploads_ia/<hash>/` para archivos temporales de sesiones de analisis IA (usa `tempfile.gettempdir()` en algunos casos para evitar conflictos de sincronizacion con Google Drive, ya que el repo vive dentro de "Mi unidad").

## 3. Decisiones de diseno relevantes

- **Placeholders DOCX partidos entre runs**: nunca editar las plantillas `.docx` directamente en Word si contienen placeholders `[[...]]`, porque Word puede volver a fragmentarlos en runs XML distintos y romper el reemplazo. `DocxGenerator._merge_runs` mitiga esto fusionando runs antes de sustituir.
- **Tablas de partidas por posicion de columna**, no por nombre de placeholder (0=desc, 1=ud, 2=cant, 3=precio, 4=total). Cualquier cambio de layout de tabla en una plantilla rompe esto silenciosamente si se reordenan columnas.
- **Numeracion de presupuesto independiente de numeracion de informe CCTV**: `f_num` (presupuesto) nunca se pre-rellena desde el informe IA; `currentNumRef` (informe) es un campo separado. Confusion aqui ha causado bugs previos (ver commits de numeracion).
- **UPLOADS en `tempfile.gettempdir()`** en vez de dentro del proyecto: el proyecto vive en una carpeta sincronizada con Google Drive, y escribir/leer archivos temporales ahi genera `WinError 2` por bloqueos de sincronizacion.
- **Servidor sin reloader** (`use_reloader=False`): decision deliberada, probablemente por conflictos de reloader con hilos de fondo (jobs async de analisis/planos). Implica que todo cambio de codigo Python exige matar y relanzar el proceso manualmente.
- **Auditoria diaria de numeracion** (`scripts/auditar_numeracion.py`): se creo tras detectar divergencias entre lo generado localmente y la carpeta de red compartida -> indica que existe un flujo de sincronizacion externo (red/NAS) no gestionado por la app misma, sujeto a desincronizacion manual.
- **Jobs asincronos con `job_id`**: tanto el analizador CCTV como el generador de planos multiples usan un patron polling (`POST` inicia el job, `GET /..._status/<job_id>` consulta progreso). Cualquier trabajo largo nuevo deberia seguir este mismo patron en vez de bloquear la request.

## 4. Problemas conocidos

- **`main.py` desactualizado**: referencia `templates/MODELO_MAESTRO.docx`, archivo que no existe en el repo actual. Si alguien intenta usar el CLI, fallara en `check_setup()`. No se ha limpiado ni actualizado.
- **Backups `.bak` y carpetas de backup sueltas en `templates/`**: `MODELO_CONTRATO_SANEAMIENTO.docx.bak`, `MODELO_MAESTRO_1OPCION.docx.bak`, `MODELO_MAESTRO_2OPCIONES.docx.bak`, y una carpeta `templates/_backup_2026-08-03_pre_fechafix`. El commit `b0d75f4` ya recupero backups sueltos del working tree; verificar si estos siguen siendo necesarios o pueden limpiarse.
- **Limite de subida de Werkzeug (413)**: hubo un fix parcial (`eab744f`) para el caso de generar PDF de un croquis con plano de fondo grande; confirmar si el limite general de tamano de subida esta bien calibrado para videos CCTV largos.
- **`tarifas/BASE_DATOS.xlsx`**: existe junto a `TARIFAS.xlsx` sin documentacion de su proposito exacto en `CLAUDE.md` ni evidencia clara en el codigo revisado en esta sesion; confirmar si esta en uso o es un artefacto residual.
- **`config/enlaces.db`**: uso no documentado explicitamente; revisar `utils/base_datos.py` antes de asumir su esquema o si esta activo en produccion (Railway usa systema de archivos efimero, por lo que un SQLite local en Railway se perderia en cada redeploy si no hay volumen persistente configurado - verificar si esto es un problema real en produccion).
- **Flujo IA de presupuesto de obra** (obra_1/obra_2 vía `/api/generar_partidas_ia`): documentado como implementado mayo 2026 pero "pendiente de prueba completa" segun `CLAUDE.md` del proyecto; no hay confirmacion en el historial reciente de que se haya validado end-to-end, en particular `stepRevisarIA` con `obra_2` (tablas `tba`/`tbb`).
- **Sincronizacion con carpeta de red**: la necesidad de un script de auditoria diaria sugiere que la copia a red no es transaccional/atomica respecto a la generacion local; posible fuente de discrepancias si el proceso se interrumpe a mitad de copia.

## 5. Proximos pasos pendientes

- Probar flujo completo: analisis CCTV -> boton "Generar presupuesto" -> generador IA de obra (obra_1 y obra_2), incluyendo `stepRevisarIA` con las dos tablas de obra_2.
- Decidir si `main.py` se actualiza para apuntar a las plantillas reales o se elimina/archiva formalmente (esta desalineado con el resto del proyecto).
- Confirmar el rol de `tarifas/BASE_DATOS.xlsx` y `config/enlaces.db`, y documentarlos en `CLAUDE.md` si siguen en uso.
- Verificar persistencia de `config/enlaces.db` y `config/subcontratas.json` en el entorno de Railway (¿volumen montado o se pierden en cada deploy?).
- Revisar si los `.bak` y la carpeta `_backup_2026-08-03_pre_fechafix` en `templates/` pueden eliminarse con seguridad.
- Enlace "Rellenar con IA" desde `stepObraTextos()` (manual) hacia `/analizar`, mencionado como posible mejora en `CLAUDE.md` del proyecto, aun no implementado.
- Mantener actualizado `CLAUDE.md` del proyecto: actualmente no menciona el editor de croquis/planos IA (`/croquis`), el chat de correccion de informes, la importacion de presupuestos/subcontratas, ni el sistema de compartir informes por token - son funcionalidades activas y deberian documentarse ahi para futuras sesiones.
