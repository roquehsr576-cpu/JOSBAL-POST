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

Copia el archivo SQLite con el servidor detenido para respaldar tus datos. Esta primera versión es para uso local: aún no incluye usuarios, facturación fiscal, integración bancaria, devoluciones ni acceso público seguro. No expongas el servidor a Internet sin implementar autenticación y un despliegue apropiado.
