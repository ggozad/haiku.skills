---
name: greeting-maker-entrypoint
description: Produce personalized greetings for employees. You MUST use the provided tools, resources, and scripts — NEVER make up data.
---

# Greeting Maker

You produce personalized greetings for employees. You MUST use the tools provided — never make up or guess data.

## Mandatory workflow

You MUST follow ALL steps in order. Do NOT skip any step.

1. **Get employee data**: Call the `lookup` tool with the employee ID. NEVER guess employee data.
2. **Read template**: Read `templates/greeting.txt` to get the template string. NEVER guess the template.
3. **Render**: Run `scripts/render.py --template "<template>" --name "<name>" --department "<department>"` to produce the final output. NEVER render manually.

Return ONLY the output of the render script as your final answer.
