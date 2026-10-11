# JOSBAL-POST

Sistema local de ventas y caja en español. Python 3.12 o superior, sin dependencias externas.

## Iniciar

```bash
cd /workspace/JOSBAL-POST
python3 app.py
```

Desde una computadora local, abre `http://127.0.0.1:8000`. En el entorno de onboarding se verifica mediante solicitudes internas; no hay una vista web pública.

1. En **Productos**, agrega nombres, precios en MXN y existencias.
2. En **Caja**, registra el fondo inicial.
3. En **Nueva venta**, selecciona productos y cobra en efectivo o registra un pago con tarjeta realizado en una terminal externa.
4. En **Caja**, registra el efectivo contado para conocer la diferencia del cierre.

Las ventas y el inventario se guardan en `data/josbal.sqlite3`. Los importes usan centavos enteros y cada venta se guarda en una transacción que descuenta existencias. El historial muestra las últimas 30 ventas.

## Validación

```bash
python3 -m unittest discover -s tests -v
```

## Configuración

- `PORT`: puerto, por defecto 8000.
- `HOST`: dirección de escucha, por defecto 127.0.0.1.
- `JOSBAL_DB`: ruta alternativa del archivo SQLite.

Copia el archivo SQLite con el servidor detenido para respaldar tus datos. Esta versión incluye una cuenta compartida configurable para acceso de red. Aún no incluye roles de usuarios, facturación fiscal, integración bancaria ni devoluciones. Para Internet utiliza HTTPS y almacenamiento permanente siguiendo la sección de Render.

## Acceso desde Internet con Render

El archivo `render.yaml` prepara un servicio de pago con disco persistente. Consulta el precio mostrado por Render antes de confirmar. No selecciones un servicio gratuito con almacenamiento temporal para datos de ventas.

1. Crea una cuenta en https://render.com y conecta GitHub.
2. Selecciona **New → Blueprint** y el repositorio `roquehsr576-cpu/JOSBAL-POST` en la rama `main`.
3. Define `JOSBAL_USER` y `JOSBAL_PASSWORD` en Render. Usa una contraseña única de al menos 16 caracteres; no la escribas en GitHub ni en un chat.
4. Revisa el plan y el disco de 1 GB antes de desplegar.
5. Cuando el servicio esté activo, abre la dirección **https://** que muestre Render. El navegador pedirá usuario y contraseña. El cifrado HTTPS lo proporciona Render.
6. Agrega un producto, abre caja, realiza una venta de prueba y revisa el cierre. Reinicia el servicio y comprueba que los registros persisten antes de introducir operaciones reales.

El servicio usa un acceso compartido mediante autenticación HTTP del navegador. No incluye cuentas individuales, roles ni cierre de sesión propio; cierra el navegador y evita dispositivos compartidos. Toda la página y la API requieren credenciales cuando hay acceso de red. Para uso local sin credenciales conserva HOST=127.0.0.1. Mantén un único servicio y disco; no escales a varias instancias con esta base SQLite. El disco conserva datos entre reinicios; no sustituye una estrategia de respaldos. La base local no se transfiere automáticamente al alojamiento.
