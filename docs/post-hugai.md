# Cambiaste un prompt y no sabes qué rompiste: evals con gate de regresión para agentes MCP

> Borrador para hugai.dev. Revisar y ajustar el tono antes de publicar. Los números salen del
> ejemplo `servicedesk-mcp` del repo (datos sintéticos), no de un sistema en producción.

## El problema

Cambias una línea del system prompt, o subes de versión el modelo, y el agente "se siente igual".
Dos semanas después alguien descubre que ahora obedece instrucciones escondidas en el texto del
usuario y llama a una herramienta destructiva. Sin evals no hay forma de saber qué cambió, ni
cuándo.

## Qué hace agent-evalkit

1. **Gold sets en YAML.** Cada caso dice qué herramientas debe llamar el agente, cuáles tiene
   prohibidas, qué debe (y no debe) decir, y si es crítico para seguridad.
2. **Runner y trazas.** Corre el agente (cualquier programa: JSON por stdin, traza por stdout) y
   guarda la traza completa: llamadas a herramientas, tokens, latencia.
3. **Jueces.** Reglas determinísticas primero; juez LLM con rúbrica para lo que las reglas no ven.
4. **Métricas.** Task success con intervalo de confianza, groundedness, costo y latencia p50/p95.
5. **Gate.** Compara candidato contra baseline y falla el PR si hay regresión.

## Un juez LLM sin calibrar es una opinión

Antes de confiar en el juez se mide su acuerdo con un humano: 50 respuestas etiquetadas a mano y
el kappa de Cohen entre juez y humano. Si el kappa baja del umbral (0.6 por defecto), el comando
sale con error y el gate puede exigir un juez calibrado. [Completar con tu kappa real cuando
tengas las 50 etiquetas; no publiques un número que no mediste.]

## El gate en acción

En el ejemplo, un prompt "v2" obedece una inyección y llama a `delete_ticket`. El PR de prueba
fue bloqueado con un comentario automático: 1 falla crítica de seguridad, task success de 100% a
83.3%, caso `sd-006` regresionado. La corrida en CI es offline y determinística: reproduce trazas
grabadas, no necesita API key y es segura para forks.

## Replay determinístico

- Las trazas guardan un hash de la entrada: si editas un caso, la traza vieja se marca obsoleta.
- Los *cassettes* congelan los resultados de herramientas para correr un agente cambiado de
  verdad: solo varía el agente. Una llamada a una herramienta que nunca se grabó aborta el caso.

## Cómo probarlo

```bash
pip install agent-evalkit
evalkit run cases/ --command "python mi_agente.py" --out baselines/main.json
```

Repo: https://github.com/hugaidev/agent-evalkit. Incluye una skill y un subagente de Claude Code
para escribir casos nuevos y proponer casos adversariales.
