# Evaluación sintética v1

El descubrimiento utiliza ruido con semilla `escenario.semilla + índice_equipo`;
las semillas efectivas quedan en `evidence[].simulation_seeds`. Validación y
reserva usan `escenario.semilla * 100 + índice_equipo` para ambas estrategias.
Se conserva esta derivación de la primera implementación; el descubrimiento
puede compartir semillas de ruido entre escenarios contiguos. No se interpreta
el ruido de cada equipo como una observación estadística independiente.

Propietario: Persona 2. Los supuestos se congelaron antes de generar candidatos;
`FORMULA_VERSION=quimica-sintetica-v1`. No describen una población real.

El generador parte de rasgos enteros uniformes 1–5. Para n=24 asigna al azar
8 personas con declaraciones sobrevaloradas, 4 subvaloradas y 12 fieles. En
cada persona sesgada altera 1–3 rasgos elegibles en 1–2 puntos, recortando a
1–5. Si todos los rasgos están en el extremo que impediría ese sesgo, modifica
un rasgo real al valor contiguo interior. Los estimados comienzan como copia
independiente de las declaraciones. No se modelan correlaciones humanas.

## Fórmula externa fija

La base es `30 + 25 * (0.7 * media_principal + 0.3 * media_secundaria - 1) / 4`.
Los rasgos principal/secundario son creatividad/extroversión para creativo,
organización/cumplimiento para técnico, cumplimiento/organización para entrega
rápida. Sobre perfiles reales, se suman:

- +22 si al menos dos miembros tienen rasgo principal >=4; −10 en otro caso.
- +8 si al menos uno tiene rasgo secundario >=4; −6 en otro caso.
- −14 si más de uno tiene liderazgo >=4; +4 en otro caso.
- Ruido uniforme [−2, 2], con score final recortado a [0, 100].

El feedback es real + ruido uniforme [−0.35, 0.35], recortado a [1, 5].
Todos los RNG son locales; ordenar IDs hace el feedback independiente del
orden del equipo. La fórmula no recibe configuración ni pesos del constructor.
Las reglas ocultas solo se revelan al final en la pantalla de jueces. La
separación de vistas evita filtraciones accidentales, no constituye control
de acceso para datos humanos.

## Manifiesto previo a candidatos

La semilla por defecto es 2026. Se fijan cinco bloques: descubrimiento y
validación del ciclo 1, descubrimiento y validación del ciclo 2, y prueba final.
Cada bloque contiene los tres tipos y cinco semillas por tipo: 15 escenarios,
cada uno con una población independiente de 24 personas. Cada escenario
produce seis equipos. La unidad de comparación es la media del escenario.

Para bloque 1–5, tipo 0–2 y repetición 0–4, las semillas de población son
`base + bloque*10000 + tipo*100 + repetición`; las de simulación añaden 1000000.
Los identificadores son `c1-discovery-{tipo}-{0..4}`, `c1-validation-...`,
`c2-discovery-...`, `c2-validation-...`, `final-...`. El manifiesto persistido
es la fuente de verdad sobre las entradas exactas de cada ejecución.

El campo `split` contiene `discovery`, `validation` o `final`; el identificador
del escenario distingue además el ciclo. En la primera integración este campo
incluía por error el prefijo de ciclo y el validador rechazaba todos los bloques
antes de compararlos. Se corrigió únicamente ese metadato, conservando las
poblaciones, los identificadores y las semillas prefijadas; una prueba conserva
su huella. Esa ejecución fallida no aporta evidencia de rendimiento.

Cada comparación usa la misma población, estimados congelados, lecciones,
semillas y 300 repartos candidatos en ambas versiones. Se informan n, medias,
desviaciones y diferencias pareadas. Aceptación: contratos y regresiones pasan,
mejora media >=2/100 y ninguna media por tipo cae más de 2. Máximo tres
candidatos por ciclo y dos ciclos. Son umbrales de demo; no son garantías
estadísticas y la validación se usa para selección. La prueba final se ejecuta
una sola vez después de elegir, se informa aunque sea desfavorable y no vuelve
al builder. Un nuevo experimento con nuevas semillas debe identificarse como tal.

El experimento longitudinal con/sin memoria es independiente de esa comparación:
la línea base no ajusta perfiles ni aplica lecciones. El error de perfil es la
media de `abs(estimado-real)` sobre las 24×5 entradas. Las asociaciones del
extractor requieren grupos de al menos tres equipos y diferencias >8 puntos;
no prueban causalidad. Las reconstrucciones con perfiles posteriores se marcan
como análisis retrospectivo. Ningún resultado obliga a mejoras monótonas.
