# Formar equipos con evidencia sintética

Propietario: Persona 3. Entradas: perfiles observables (sin `real`), resultados
anteriores, tipo de proyecto y lecciones. Salida: hipótesis estructuradas con los
diez campos de Química. `agentes/reflexionador.py` carga y valida la política JSON
siguiente; las pruebas verifican que se utiliza para la extracción. No ejecuta
instrucciones arbitrarias de este archivo.

```json
{"schema_version": 1, "umbral": 4, "cantidades": [0, 1, 2, 3], "operadores": ["min", "max"], "minimo_por_grupo": 3, "diferencia_minima": 8}
```

Para cada rasgo, umbral, operador y cantidad, separar equipos según cumplimiento
con las estimaciones observadas en su ejecución. Exigir los tamaños de muestra
de la política y una diferencia estrictamente mayor a 8 a favor de la regla.
La identidad incluye tipo, rasgo, operador, umbral **y cantidad**. Registrar las
medias, tamaños y referencias de los resultados fuera de la lección.

Si solo hay estimaciones actuales, identificar el análisis como retrospectivo.
La asociación no demuestra causalidad. `min` significa al menos esa cantidad y
`max`, como máximo esa cantidad. El constructor base compara 300 repartos,
minimiza incumplimientos y desempata por la varianza normalizada entre medias de
equipo. La estrategia versionada tiene su propio objetivo explícito.

La ayuda del curador se mide respecto del promedio histórico **previo** del tipo;
es una heurística y no reemplaza la comparación externa reservada. No se reciben
rasgos reales, reglas ocultas, escenarios finales ni instrucciones ejecutables.
