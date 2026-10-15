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

Copia el archivo SQLite con el servidor detenido para respaldar tus datos. Esta versión incluye cuentas individuales con roles, cancelaciones registradas y respaldos. Aún no incluye facturación fiscal ni integración bancaria. Para Internet utiliza HTTPS y almacenamiento permanente siguiendo la sección de Render.

## Acceso desde Internet con Render

El archivo `render.yaml` prepara un servicio de pago con disco persistente. Consulta el precio mostrado por Render antes de confirmar. No selecciones un servicio gratuito con almacenamiento temporal para datos de ventas.

1. Crea una cuenta en https://render.com y conecta GitHub.
2. Selecciona **New → Blueprint** y el repositorio `roquehsr576-cpu/JOSBAL-POST` en la rama `main`.
3. Define `JOSBAL_USER` y `JOSBAL_PASSWORD` en Render. Usa una contraseña única de al menos 16 caracteres; no la escribas en GitHub ni en un chat.
4. Revisa el plan y el disco de 1 GB antes de desplegar.
5. Cuando el servicio esté activo, abre la dirección **https://** que muestre Render. El navegador pedirá usuario y contraseña. El cifrado HTTPS lo proporciona Render.
6. Agrega un producto, abre caja, realiza una venta de prueba y revisa el cierre. Reinicia el servicio y comprueba que los registros persisten antes de introducir operaciones reales.

El administrador principal conserva el acceso configurado en Render. Las cuentas individuales usan la pantalla `/login`, sesiones y cierre de sesión propio. La caja y sus API requieren credenciales; la carta `/menu` es pública. Para uso local sin credenciales conserva HOST=127.0.0.1. Mantén un único servicio y disco; no escales a varias instancias con esta base SQLite. El disco conserva datos entre reinicios; no sustituye una estrategia de respaldos. La base local no se transfiere automáticamente al alojamiento.

## Menú digital Josbal Café

- Carta para clientes, sin contraseña: `/menu`. Incluye búsqueda, categorías y descarga de la carta PDF original.
- El PDF proporcionado por el propietario se transcribió en `catalog/menu.json`: 158 entradas cobrables en 27 categorías, contando tamaños chico/grande y el extra de $5 para cambiar a papas gajo.
- En el primer inicio tras esta actualización se agregan automáticamente al catálogo y a la base persistente. Reiniciar no duplica productos ni restablece precios editados; no se sobrescriben productos previos ni ventas.
- Las entradas de carta se crean como **Preparado al pedido (sin conteo)** porque el documento no indica cantidades. En Productos puedes activar **Controlar existencias** y registrar el stock real.
- Puedes editar precio, nombre, categoría y descripción desde Productos; esos cambios se reflejan en la carta pública de las entradas importadas. Los productos previos o creados manualmente no se publican automáticamente.
- El menú público muestra únicamente nombres, precios, categorías y descripciones. La caja, inventario, historial y operaciones siguen protegidos por contraseña.
- `JOSBAL_IMPORT_MENU=0` desactiva la incorporación automática para pruebas o instalaciones que no requieran esta carta. No elimina productos que ya se hayan importado.

## Indicaciones de preparación

En **Nueva venta**, selecciona un producto y selecciona las opciones de preparación correspondientes a su categoría o escribe otras indicaciones. Pulsa **Agregar a la venta**. Para dos unidades con preparaciones distintas, selecciona el producto de nuevo y elige otras indicaciones: quedan en líneas separadas. El botón **+** incrementa la misma preparación; **Indicaciones** permite cambiarla para todas las unidades de esa línea. Las indicaciones no modifican el precio y deben confirmarse con cocina. Tras cobrar, se guardan junto con los productos en **Historial → Ver detalle**, incluso después de reiniciar. La consulta de estos detalles requiere autenticación. La carta pública sigue siendo una carta de consulta; los pedidos se registran desde la caja.

## Mesas y pedidos pendientes

1. En **Mesas**, pulsa **Agregar mesa** y escribe un nombre como “Mesa 1” o “Terraza 2”. Puedes renombrarla o desactivarla desde **Configurar**. No hay mesas ficticias precargadas.
2. Pulsa **Tomar pedido**, agrega los productos y sus indicaciones y pulsa **Guardar pedido de mesa**. Se guarda un pedido pendiente por mesa en SQLite, visible desde otros dispositivos al recargar la página.
3. Desde **Mesas → Ver pedido**, continúa agregando productos o cobra. Al cobrar se libera el pedido pendiente, se descuenta inventario y se registra la mesa en **Historial → Ver detalle**.
4. Para atender otra mesa, guarda o cobra primero el pedido actual. Los cambios aún no guardados del carrito no se conservan al recargar. **Mostrador / para llevar** permite vender sin asignar mesa.

Los pedidos guardados sobreviven a reinicios y no se contabilizan como ventas hasta cobrarlos. No reservan existencias: disponibilidad y precios se verifican de nuevo al cobrar. Si otro dispositivo modifica o cobra el mismo pedido, el sistema rechaza operaciones con la versión antigua; recarga la página y vuelve a abrir la mesa. Una mesa con pedido pendiente no se puede desactivar. Renombrar una mesa no cambia el nombre guardado en ventas anteriores. La configuración y los pedidos son privados; no aparecen en la carta pública.

## Cambios y cancelaciones con motivo

- **Quitar o cambiar productos de un pedido ya enviado:** en la mesa, usa **−** o cambia las indicaciones y pulsa **Guardar y enviar comanda** o **Cobrar venta**. El sistema pide el motivo antes de guardar. Agregar productos no requiere motivo.
- **Cancelar un pedido pendiente:** en la mesa, pulsa **Cancelar pedido de la mesa** y elige el motivo. Cocina y Barra reciben el aviso de no preparar lo que siga pendiente.
- **Cancelar una venta cobrada:** en **Historial → Ver detalle**, pulsa **Cancelar venta**. Solo aplica a ventas del turno de caja abierto. La venta queda en el historial marcada como **CANCELADA**, se descuenta del corte de caja sin devolver existencias automáticamente. La devolución del dinero se entrega en efectivo o en la terminal de tarjeta por separado.
- Motivos disponibles: cliente cambió de opinión, error al tomar el pedido, producto agotado, demora en el servicio, problema de calidad u otro (con descripción obligatoria). Puedes agregar detalles en todos los casos.
- **Cambios** muestra los últimos 200 registros con fecha, mesa, venta, comanda, productos, importe y motivo, y un resumen por motivo para detectar qué mejorar. Los registros no se pueden borrar desde la aplicación.

## Imágenes del menú

Las 27 categorías de la carta incluyen imágenes ilustrativas generadas con estilo de fotografía natural. Se muestran en la carta pública y en la caja; cada producto utiliza la imagen representativa de su categoría, no una fotografía exacta de cada variante. El aviso de imágenes ilustrativas es visible en ambas vistas. Las imágenes se sirven desde el mismo servidor, sin enlaces externos. El archivo `static/images/menu-photos.png` contiene las imágenes en una cuadrícula uniforme y `static/food-images.js` asigna cada categoría a su imagen. Las categorías nuevas sin una ilustración asignada conservan el diseño de texto.


## Opciones de preparación según el producto

- Hamburguesas, con o sin papas: sin cebolla, picante, mostaza, mayonesa o cátsup.
- Frappés: sin azúcar añadida, crema batida o chocolate.
- Tés, tizanas calientes y bebidas calientes: sin azúcar añadida.
- Bebidas sobre las rocas: sin azúcar añadida o sin hielo.
- Otras categorías: campo de indicaciones escritas, sin casillas de ingredientes de hamburguesa.

En **Productos → Editar → Opciones de preparación** puedes elegir un grupo distinto para un producto o **Solo indicaciones escritas**. El valor predeterminado es **Automáticas según categoría**. Las indicaciones de pedidos previos se conservan aunque cambies el grupo; las que ya no tienen una casilla correspondiente aparecen en el campo de texto. “Sin azúcar añadida” no indica que la bebida esté libre de azúcar.

Validación de estas reglas: `node tests/test_preparation_options.js` (Node.js) además de las pruebas Python de ventas, pedidos y persistencia.

## Comandas separadas para Cocina y Barra

Una cuenta de venta conserva el total completo, pero su preparación se separa en dos tickets relacionados por el mismo **número de comanda** y **mesa**.

1. Toma el pedido de una mesa con alimentos y bebidas. No es necesario abrir caja para enviar una comanda; sí para cobrar.
2. Pulsa **Guardar y enviar comanda**. Cocina recibe sus platos y Barra recibe bebidas, postres y croissants, con cantidades e indicaciones. Un área sin productos no recibe un ticket vacío.
3. En el dispositivo de Cocina abre `/cocina`; en el de Barra abre `/barra`. Inicia sesión con las credenciales del sistema. Las pantallas consultan nuevos pedidos cada 5 segundos mientras permanecen abiertas y conectadas.
4. Cada área puede marcar su ticket como **En preparación** o **Lista**, de manera independiente. **Mostrar listas recientes** muestra hasta las últimas 50 comandas listas además de las pendientes.
5. Pulsa **Ver / imprimir ticket** y después **Imprimir este ticket**. El navegador abre el diálogo de impresión: selecciona la impresora de esa área y ajusta papel/márgenes para tu equipo. Esto no realiza impresión automática ni envía trabajos directamente a una impresora remota. Los tickets solo contienen productos de su área; son comandas de preparación, no comprobantes fiscales ni de pago.
6. Al cobrar un pedido enviado, se conserva el número de comanda y el estado de preparación. No se duplica el envío si los productos no cambiaron. Una venta directa de mostrador genera sus comandas al cobrar.

Las bebidas, waffles, pasteles, postres, croissants dulces y salados y crepas se asignan automáticamente a Barra. Los demás platos y extras van a Cocina. En **Productos → Editar → Área de preparación** puedes cambiar el destino a Cocina o Barra por producto, cuando un producto se prepare en una estación distinta.

Si se modifica un pedido enviado, solo las áreas cuyo contenido cambió vuelven a **Pendiente**. Su ticket muestra **COMANDA MODIFICADA**, el contenido anterior y el actual para revisar lo agregado o retirado. No vuelvas a preparar automáticamente toda la lista. Una actualización que retire todos los productos de un área conserva un aviso explícito de retirada para ese equipo. Los tickets e indicaciones sobreviven a reinicios. Las comandas nuevas se generan al guardar/enviar o cobrar: esta actualización no reenvía ventas antiguas ni pedidos previos de forma automática; abre y guarda un pedido previo para enviarlo.

Puedes consultar los tickets de una comanda específica mediante `/cocina?pedido=NUMERO` o `/barra?pedido=NUMERO`. El detalle de venta incluye enlaces a ambas áreas. Cocina, Barra, tickets y sus API requieren autenticación y no se exponen en el menú público. Puedes iniciar sesión con una cuenta de administrador, cajero o mesero; solo administradores y cajeros pueden modificar los estados de preparación.


## Cancelar cobro y devolver inventario son acciones separadas

**Cancelar venta** registra el motivo, ajusta el corte y retira lo pendiente en preparación. No suma existencias, incluso cuando la comida se haya preparado o descartado. La devolución del dinero sigue siendo manual: en efectivo o en la terminal de tarjeta.

Tras cancelar, en **Historial → Ver detalle → Devolver unidades al inventario** selecciona explícitamente solo las unidades no preparadas y recuperables que realmente regresan. Introduce un motivo. Puedes devolver parcialmente; el sistema impide superar las cantidades descontadas o devolver dos veces las mismas unidades. Solo aplica a productos que controlan existencias. Este movimiento queda en **Cambios**, sin alterar el cobro ni el corte. Las cancelaciones anteriores a esta actualización, que ya devolvieron stock automáticamente, se registran como devoluciones anteriores al migrar para impedir una segunda devolución.

## Quitar mesas de prueba

En **Mesas → Configurar → Quitar mesa** se retira la mesa de la lista sin borrar ventas, motivos ni comandas anteriores. Si tiene un pedido pendiente, abre **Ver pedido → Cancelar pedido de la mesa** y registra el motivo primero. Para pruebas puedes elegir **Otro** e indicar “Pedido de prueba”. Si la venta ya fue cobrada, cancelarla es una operación distinta en Historial; quitar una mesa no cancela cobros. Puedes volver a agregar el mismo nombre de mesa más adelante.


## Usuarios y permisos

Abre `/login` e ingresa el usuario y contraseña del administrador principal que configuraste en Render (`JOSBAL_USER` y `JOSBAL_PASSWORD`). Esa cuenta permanece como administrador y se modifica en Render, no desde la lista de usuarios. En **Administración → Agregar usuario**, crea cuentas propias con contraseñas de 16 a 200 caracteres y el rol correspondiente:

| Rol | Permisos |
| --- | --- |
| Administrador | Productos, precios, configuración de mesas, pedidos, caja, cobros, cancelaciones, inventario, usuarios y respaldos. |
| Cajero | Abrir/cerrar caja, tomar pedidos, cobrar, consultar historial y modificar estados de preparación. No puede cancelar ni cambiar precios. |
| Mesero | Ver catálogo y mesas, tomar y guardar pedidos, consultar comandas. No puede cobrar, cancelar, manejar caja ni ver historial de ventas. |

Los permisos se validan en el servidor, no solo ocultando botones. Las acciones exitosas de modificación guardan usuario, rol, fecha y acción en un registro privado (`/api/audit`, últimas 200 entradas). Las contraseñas se guardan con sal individual y PBKDF2-SHA256, sin valores legibles; no se devuelven en las API. Las sesiones duran hasta 12 horas y las cookies usan HttpOnly, SameSite=Strict y Secure cuando HOST no es loopback (acceso público mediante HTTPS). Editar, desactivar o cambiar la contraseña de una cuenta revoca sus sesiones. **Cerrar sesión** lleva a `/login`; una sesión revocada no vuelve automáticamente al acceso básico que haya quedado guardado en el navegador. Diez intentos fallidos por nombre de usuario bloquean temporalmente la autenticación durante un minuto.

Para probar localmente sin usuarios sigue disponible el modo loopback sin credenciales. Si creas cuentas en ese modo, la primera debe ser un administrador activo; al crearla se desactiva el acceso anónimo. No se crean empleados ni contraseñas predeterminadas.

## Respaldos automáticos y recuperación

El servidor crea una copia íntegra de SQLite al iniciar y cada 6 horas mientras está ejecutándose, y conserva las últimas 14 copias en `backups/` junto a la base (`/var/data/backups` en Render). Antes de migrar una base existente crea una copia previa. Usa la API de backup de SQLite para obtener una copia consistente con el servidor activo y comprueba `PRAGMA integrity_check`. En **Administración → Respaldos** puedes crear una copia inmediata y descargarla; solo administradores tienen acceso. Los errores de respaldo se muestran en esa sección. `JOSBAL_BACKUP_DIR` permite configurar otro directorio persistente.

Estas copias comparten el disco con la base: protegen frente a cambios de datos, pero no frente a perder o eliminar todo el disco. Descarga periódicamente una copia y guárdala fuera de Render. Los archivos contienen información privada del negocio y hashes de cuentas; no los publiques. No está configurada una copia automática hacia un proveedor externo.

Para verificar la recuperación en una copia nueva, sin sobrescribir la base en uso:

```bash
python3 backups.py /ruta/al/respaldo.sqlite3 /ruta/nueva/recuperada.sqlite3
```

El comando valida integridad y crea una base separada, sin sobrescribir un destino existente. Las sesiones de la copia recuperada se eliminan para no reactivar sesiones antiguas. Luego puedes probarla en otra instancia local con `JOSBAL_DB=/ruta/nueva/recuperada.sqlite3 PORT=8001 python3 app.py`. El reemplazo de la base de producción requiere una recuperación controlada con el servicio detenido; este comando no la reemplaza.

## Revisar el pedido desde el celular

En **Nueva venta** aparece un botón fijo inferior **Ver pedido**, con cantidad de productos, mesa y total. Abre un resumen con nombres, cantidades e indicaciones para repetir la orden al cliente antes de enviarla. Desde ahí puedes cambiar indicaciones, seguir agregando o **Confirmar y enviar comanda**. El resumen no guarda por sí solo: debes confirmar el envío para conservar el pedido. **Ir a mesa y cobro** lleva al panel completo; las opciones de cobro siguen restringidas por rol.


### Enviar comandas desde el resumen móvil

En **Ver pedido** puedes seleccionar la mesa directamente y pulsar **Confirmar y enviar comanda**, incluso con la caja cerrada. Abrir caja sigue siendo obligatorio para cobrar. En el panel completo, el texto sobre **Guardar y enviar comanda** indica si faltan productos o seleccionar mesa; el botón deja de bloquearse por el estado de la caja. Los pedidos e indicaciones se conservan al abrir el panel completo.

## Avisos de pedidos listos

En la caja y en el celular del mesero pulsa **Activar avisos con sonido** una vez. Sonará una prueba. Después, cuando Cocina o Barra marque una comanda como **Lista**, aparece un aviso con área, mesa y número de comanda y suena un timbre corto si el navegador permite audio. Si todas las áreas con productos están listas, el aviso indica **Pedido completo**; de lo contrario indica que la otra área aún debe revisarse. **Enterado** retira el aviso de ese dispositivo; no cambia la comanda.

Se consultan eventos cada 5 segundos. Cada transición nueva a Lista genera un evento persistido; no se repite por cobrar el pedido ni por consultar de nuevo con el mismo cursor. La primera carga comienza a escuchar eventos nuevos, sin hacer sonar comandas antiguas. Reabrir y volver a marcar Lista genera un nuevo aviso. Los tickets vaciados por retirada/cancelación no generan un aviso de preparación terminada.

Mantén JOSBAL abierto y con volumen audible. Los navegadores móviles pueden suspender el audio y la consulta con la pantalla bloqueada o la aplicación en segundo plano; no son notificaciones push. Si se suspende el audio, vuelve a activar el botón. Los avisos visuales funcionan sin habilitar sonido. No se ha configurado envío por WhatsApp ni sonido con el navegador cerrado.

## Archivar historial de ventas

Solo administradores pueden archivar o restaurar ventas. En **Historial → Ver detalle → Archivar venta** se oculta una venta del historial principal; **Archivar ventas mostradas** archiva únicamente la página visible, hasta 30 ventas. La pantalla pide confirmar. El selector **Ventas archivadas** permite consultar los registros y sus detalles, y restaurarlos individualmente o por página. **Ver anteriores** recorre el historial por páginas.

Archivar no elimina registros, no cancela cobros y no modifica caja, inventario, comandas ni ajustes. Las ventas archivadas siguen incluidas en el corte del turno al que pertenecen. Se guarda quién archivó cada venta y cuándo, y se registra la acción en auditoría. Para anular una venta de prueba cobrada usa su cancelación por separado cuando proceda; archivar solamente cambia su visibilidad. No se archivan ventas automáticamente al instalar esta función.
