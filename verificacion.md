# Verificación de TEAMFORGE

Fecha: 2026-11-09. Python 3.12.14; objetivo Python 3.11+. Núcleo sin API ni dependencias externas.

## Comprobaciones ejecutadas

- `python main.py demo`: diez rondas; JSON base con exactamente cuatro claves.
- `python main.py evolucion --reiniciar`: dos ciclos, seis candidatas, decisiones persistidas y reserva final.
- `python -S main.py aplicar`: aplicación posterior con la versión activa cargada desde SQLite; seis equipos.
- `python -S main.py evolucion`: recupera el experimento guardado, sin volver a ejecutar la reserva.
- `python -S -m unittest discover -s tests -v`: **44 pruebas aprobadas**. `-S` deshabilita paquetes externos de site-packages.
- Compilación Python completa; AppTest Streamlit y Chromium: cuatro pestañas, dos gráficas, generación/lectura de lote, sin excepciones ni errores JS. Vista móvil de 390 px sin desbordamiento horizontal.
- CLI rechaza repartir el lote de 10 sin divisibilidad entre cuatro; no descarta ni duplica participantes.

## Resultados observados

| Conjunto | Escenarios | Media anterior | Media elegida | Cambio | DE de diferencias |
| --- | ---: | ---: | ---: | ---: | ---: |
| Validación del ciclo 2 | 15 | 53.689 | 57.156 | +3.467 | 5.074 |
| Prueba final reservada | 15 | 51.506 | 53.395 | +1.889 | 5.901 |

Cada conjunto contiene cinco escenarios por tipo y seis equipos por escenario. La unidad de resumen es el escenario. La reserva no confirmó una mejora media de al menos dos puntos: no se ajustó la versión después de observarlo. En entrega rápida el cambio reservado fue −0.333 puntos. No es evidencia de mejora universal.

| Ciclo | Candidata | Cambio en validación | Decisión |
| --- | --- | ---: | --- |
| 1 | `strategy-2555935595a09b9e` | +0.578 | Rechazada |
| 1 | `strategy-f339d4ce6e40ad01` | +1.333 | Rechazada |
| 1 | `strategy-a0d6f9f10996aa47` | -0.178 | Rechazada |
| 2 | `strategy-bf695fd024d27428` | +3.467 | Apta |
| 2 | `strategy-1a8102c32060db63` | +2.089 | Apta |
| 2 | `strategy-b0ebedfc637a4b8d` | +1.489 | Rechazada |

Dos candidatas superaron todos los controles; la referencia activa apunta a la de mayor mejora. Además, existe un rechazo de pesos inválidos introducido expresamente para probar el mecanismo.

## Una cadena concreta de evidencia

1. Snapshot público: `evidence-c1-discovery-creativo-0`; equipos y perfiles observados se conservan en `evolucion.json → evidence`.
2. Hipótesis `lec-93eb95c9790a7bad`: Hipótesis: al menos 2 miembros con creatividad >= 4 se asocia a +15.25 puntos en creativo; n=17/13. No demuestra causalidad.
3. Evidencia asociada: 17 equipos cumplen y 13 no; diferencia observada 15.254. Los IDs de resultados constan en `lesson_evidence`.
4. Caso `case-c12b0c79ebe955d1`: máximo 18 incumplimientos agregados de las lecciones del snapshot. La anterior registra 19 y falla; la elegida registra 14 y pasa. La hipótesis se aplica retrospectivamente sobre los mismos equipos y perfiles congelados, nunca perfiles posteriores.
5. Configuración `strategy-bf695fd024d27428`: pesos {'balance': 0.3, 'lessons': 0.7}; presupuesto 300, prioridades explícitas de lecciones. Pasa las seis regresiones acumuladas y la comparación externa fija.
6. Aplicación siguiente `application-70ea4c2d725f827886c5` utiliza esa misma versión para formar 6 equipos nuevos y guardar feedback y actualización de perfiles en `aplicacion.json`.

## Integración y límites

Una corrida preliminar contenía etiquetas de split incompatibles e impedía comparar candidatas. Se corrigieron los metadatos sin cambiar poblaciones, semillas, fórmula ni umbrales; esa corrida se conserva en SQLite como `auditoria-etiquetas` y no cuenta como evidencia de rendimiento. Las pruebas de integración cubren el error.

La generación de regresiones se endureció para exigir coincidencia con los equipos observados. Se conservaron todas las seis regresiones de esta ejecución. Las pruebas validan ese requisito.

La demo separa el experimento longitudinal de la comparación de estrategias. Los perfiles sintéticos no representan datos humanos validados. SDK/API, MCP, feedback humano y controles de privacidad individual quedan pendientes. El repositorio local no está publicado.

Los archivos del paquete incluyen código, pruebas, documentación, exportaciones, SQLite y un bundle de los hitos Git. El entorno virtual no se incluye. Para reconstruir solo el código con historial: `git clone historial.bundle teamforge-codigo`. Para ejecutar inmediatamente, usa los archivos de la carpeta TEAMFORGE y sigue README.md.
