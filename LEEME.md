# App Benitooo con actualización automática (16-17/11/2026)
- `index.html`: la app. Al abrirse (y cada 10 min, y con el botón "Actualizar") lee `datos.json`. Si no puede, usa los datos que lleva dentro.
- `datos.json`: ahora mismo es la copia de los datos de la app anterior (hasta el 8/11). Lo sustituirá el robot.
- Formato: `{"jor":[{"j":13,"ms":[{"h","a","d","t","arb","ali","g","c","k","s","bw"}]}],"meta":{"act","datos"}}`.
  `bw` (nuevo, opcional) = cuotas de bwin por selección: `{"Goles: más de 2,5": 1.85}`. Si existe, la app la usa en vez de la cuota estimada; si Benito escribe una a mano, gana la suya.
- Probado solo la sintaxis del código. Falta probarlo en el navegador una vez publicado.

## Falta para que se actualice sola (lo hará el robot)
1. Cuenta de GitHub conectada a Claude (lo hace Benito).
2. Clave gratuita de API-Football (alineaciones, bajas, árbitro, calendario) (la crea Benito).
3. Clave de un servicio con cuotas de bwin (la crea Benito; ver si el plan gratis las incluye).
4. Script `generar_datos.py` (recalcula con el modelo y escribe datos.json) y el robot de GitHub (`actualizar.yml`) que lo ejecuta cada pocas horas. Se escriben y prueban cuando existan las claves.
