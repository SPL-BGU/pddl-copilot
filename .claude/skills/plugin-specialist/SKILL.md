---
name: plugin-specialist
description: Research-driven Claude Code plugin specialist. Fetches current docs, studies real plugins from marketplaces, recommends simplest architecture. Use when creating a new plugin, choosing architecture tier, or researching plugin patterns.
context: fork
agent: plugin-specialist
argument-hint: [question or topic]
---

Consult the plugin specialist about Claude Code plugin development.

$ARGUMENTS

The specialist will research current documentation and study real plugins from official and community marketplaces before answering. It recommends the simplest architecture tier that works (Docker is a last resort). It uses `plugins/pddl-planning-copilot/` as a local reference but notes that it is a Tier 3 (Docker) plugin — most new plugins should be simpler.
