# Declaração de uso de IA

## Ferramenta e modelo

- **Ferramenta:** Claude (claude.ai, modo agente com acesso a shell/arquivos em ambiente isolado)
- **Modelo:** Claude Opus 5.5 (`claude-opus-5-5`), da Anthropic
- **Sessões:** 1 (ver `sessao.md`)

## O que a IA fez

- Leu o README, o código-fonte, os testes e os dados do desafio.
- Rodou o estado original (testes e CLI) para registrar a linha de base.
- Identificou os 5 defeitos e aplicou as correções em `src/`.
- Escreveu um cálculo de referência independente e comparou com o relatório gerado (amostra e dataset completo).
- Escreveu os testes adicionais em `tests/test_additional_rules.py`.
- Redigiu `entrega/README-ENTREGA.md`, esta declaração e o log da sessão.

## O que eu fiz

- Forneci o pacote do desafio e pedi a resolução.
- Rodei o projeto no GitHub Codespaces, executei pytest -q (34 passed) e o CLI no dataset completo, conferi o resultado com a amostra do README e publiquei o repositóri

## Observação

Os testes fornecidos não foram alterados. Todas as mudanças de código estão descritas, com causa raiz,
em `entrega/README-ENTREGA.md`.
