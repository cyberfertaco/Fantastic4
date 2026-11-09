# Guion de demo — Persona 4

## Preparación

Dentro del entorno virtual, ejecuta:

```bash
python main.py demo
python main.py evolucion
python main.py aplicar --id demo-evolucion --tipo creativo --semilla 43
python -m unittest discover -s tests
streamlit run app.py
```

Conserva como respaldo las exportaciones `resultados/metricas.json` y
`resultados/evolucion.json`, junto con `datos/teamforge.sqlite3`. La interfaz
lee esas ejecuciones; si falta un resultado, muestra el comando para generarlo.
Reserva los últimos 45 minutos del hackathon para comprobaciones, ensayo y
copia de estos archivos, sin añadir integraciones.

## Recorrido de cinco minutos

1. **Rondas.** Explica que son 24 personas sintéticas y diez rondas. Compara las
   dos gráficas: score externo y error de estimación. La línea base no actualiza
   perfiles. La variación entre rondas también cambia el tipo de proyecto; no
   se presenta una curva ascendente como condición de éxito.
2. **Memoria y evidencia.** Elige una lección, lee su condición y abre la
   observación vinculada. Muestra su uso y ayuda frente al promedio histórico
   previo. La asociación es una hipótesis; el indicador del curador no acepta
   versiones por sí mismo.
3. **Estrategias.** Selecciona una decisión y sigue la cadena: snapshot de
   descubrimiento → lección → propuesta y diferencias JSON → caso de regresión
   → comparación externa → motivo de aceptación o rechazo. Abre los controles
   para comprobar el fallo anterior y el resultado de la candidata.
4. **Continuidad.** La tabla de ciclos muestra la versión que entra y sale de
   cada ciclo. Una candidata aceptada se utiliza en el siguiente; si ninguna
   pasa, permanece la anterior. Muestra un rechazo empírico si existe, y por
   separado el rechazo preparado que comprueba el mecanismo. «La siguiente
   formación» muestra la versión realmente aplicada, sus equipos y feedback
   en una ejecución posterior; el comando `aplicar` no ajusta la estrategia.
5. **Prueba reservada.** Lee el resultado final con tamaño de muestra y
   dispersión, incluso si es desfavorable. Se ejecuta después de elegir y no
   sirve para seguir ajustando. Termina con la generación de un lote; verifica
   que los lotes previos siguen presentes.

## Qué decir con precisión

«TEAMFORGE mejora iterativamente configuraciones de formación de equipos a
partir de resultados sintéticos. Un evaluador fijo decide qué propuestas
aceptar. No reentrena un modelo ni cambia su propio código».

Si no hay una aceptación, dilo: «La ejecución produjo evidencia y decisiones
reproducibles, pero ninguna candidata demostró la mejora exigida». No rellenes
gráficas ni cambies las semillas para mejorar el relato.

La verdad sintética y las reglas ocultas aparecen en la revelación para jueces
de **Perfiles**. Esa pantalla no demuestra controles de privacidad para
personas reales. El modo entregado es determinista; SDK/API y MCP son trabajo
futuro.
