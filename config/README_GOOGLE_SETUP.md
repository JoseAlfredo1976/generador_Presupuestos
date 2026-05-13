# Configuracion Google Sheets API

## Pasos para activar el registro automatico de presupuestos

### 1. Crear cuenta de servicio en Google Cloud

1. Ve a https://console.cloud.google.com/
2. Crea un proyecto nuevo (ej: "Presupuestos Grupo Europa") o usa uno existente
3. En el menu lateral: APIs y servicios > Biblioteca
4. Busca "Google Sheets API" y actívala
5. Ve a APIs y servicios > Credenciales
6. Clic en "Crear credenciales" > "Cuenta de servicio"
7. Nombre: "presupuestos-app" > Crear y continuar > Listo
8. Clic en la cuenta de servicio recien creada
9. Pestana "Claves" > Agregar clave > Crear clave nueva > JSON
10. Se descarga un archivo JSON. Renobrarlo a: google_credentials.json
11. Copiarlo a esta carpeta: budget_generator/config/google_credentials.json

### 2. Compartir la hoja de calculo

1. Abre el archivo google_credentials.json con un editor de texto
2. Copia el valor del campo "client_email" (algo como presupuestos-app@....iam.gserviceaccount.com)
3. Abre la hoja de Google Sheets
4. Clic en "Compartir" (arriba a la derecha)
5. Pega el email de la cuenta de servicio
6. Dale permisos de "Editor"
7. Clic en Enviar

### 3. Verificar

Reinicia la app. En el paso de contrato/direccion aparecera automaticamente
el siguiente numero de presupuesto sugerido. Al generar el documento,
se registrara en la hoja correspondiente.

### Estructura esperada en Google Sheets

Cada pestaña debe tener estas columnas (la app las crea automaticamente si no existen):
- Columna A: Nº Presupuesto
- Columna B: Fecha
- Columna C: Cliente
- Columna D: Obra / Servicio
- Columna E: Importe sin IVA
- Columna F: Tipo
- Columna G: Carpeta

Pestanas necesarias (la app las crea si no existen):
- POCERIA
- FONTANERIA
- ALBANILERIA
- LIMPIEZAS
- CCTV-LIMPIEZAS
- PLAN SEGURIDAD
- CONTRATOS
- SUBCONTRATAS
