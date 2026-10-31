"""sandbox — безопасное выполнение кода ученика (Design §13.2).

Слои: статический AST-анализ → RestrictedPython 8.5 → ограниченные
builtins/гварды → белый список импортов → subprocess с лимитами
(RLIMIT_AS / Job Object, per-run timeout, обрезка вывода 64 КБ).
Порт app/core/{sandbox_runtime, sandbox_limits, executor} из teacher (§20.1).
"""
