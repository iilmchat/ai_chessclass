"""llm — единый LLM-шлюз RouterAI (Design §8): client, routes, registry, gateway.

Все LLM-вызовы системы проходят через llm.gateway; домены знают только
маршрут `<domain>.<op>` и уровень ученика (ADR-004).
"""
