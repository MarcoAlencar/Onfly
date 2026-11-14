# Entrega — Consolidador de reservas de hotel (Onfly)

## Resumo

O CLI tinha **5 defeitos** independentes. Todos foram corrigidos com mudanças pontuais (13 linhas
adicionadas, 7 removidas em `src/`), sem alterar o comando, os argumentos, o schema do relatório,
os dados nem os testes fornecidos.

| | Antes | Depois |
|-|-|-|
| `pytest -q` (testes fornecidos) | 5 failed | 5 passed |
| `pytest -q` (fornecidos + adicionais) | — | **34 passed** |
| Amostra `exemplo-validacao.csv` | noites `-33`, total `5962.41` | idêntica à tabela do README |
| `reservas_hoteis.csv` — reservas lidas | 200 | **300** |
| `reservas_hoteis.csv` — noites | -1393 | **1347** |
| `reservas_hoteis.csv` — total BRL | 193218.53 | **396170.00** |

## Defeitos corrigidos

### 1. Reservas descartadas após a 200ª linha
- **Arquivo:** `src/onfly_report/repositories/csv_reservation_repository.py`
- **Causa raiz:** o laço de leitura tinha um `if len(rows) == 200: break`, que truncava silenciosamente o arquivo (o dataset tem 300 reservas).
- **Correção:** removido o limite; todas as linhas são lidas.

### 2. Noites calculadas pelo dia do mês
- **Arquivo:** `src/onfly_report/services/stay_calculator.py`
- **Causa raiz:** usava `checkout.day - checkin.day`, que subtrai só o dia do mês e gera valores errados/negativos na virada de mês/ano (30/01 → 02/02 dava `-28`).
- **Correção:** `(checkout - checkin).days * rooms`.

### 3. `NO_SHOW` tratado como faturável
- **Arquivo:** `src/onfly_report/services/status_policy.py`
- **Causa raiz:** a regra era uma lista negativa (`status != "CANCELLED"`), então `NO_SHOW` (e qualquer outro status) entrava em noites, valores, `by_month` e `top_hotels`.
- **Correção:** lista positiva — só `status == "CONFIRMED"` é faturável.

### 4. Câmbio invertido e em `float`
- **Arquivo:** `src/onfly_report/services/currency_converter.py`
- **Causa raiz:** fazia `float(amount) / float(rate)` — dividia em vez de multiplicar e passava por `float`, perdendo exatidão.
- **Correção:** `amount * rate` em `Decimal` puro. Extra: moeda sem taxa agora gera `InputFileError` (saída `2`, entrada inválida) em vez de `KeyError` (saída `1`).

### 5. Ranking de hotéis em ordem crescente
- **Arquivo:** `src/onfly_report/services/report_builder.py`
- **Causa raiz:** o `sorted` usava a chave `(amount, hotel_id)` sem inverter o valor, então o `top_hotels` listava os hotéis de **menor** faturamento.
- **Correção:** chave `(-amount, hotel_id)` — `total_brl` decrescente com desempate por `hotel_id` ascendente, como pede o README.

## Como investiguei

1. **Li o README como especificação** e listei cada regra verificável (status, noites, câmbio, exatidão, ordenação, contrato do CLI).
2. **Rodei o estado original** (`pytest -q` → 5 falhas; CLI na amostra → noites negativas, total errado) para ter a linha de base.
3. **Percorri o pipeline na ordem do README** (`ler → converter tipos → contar status → filtrar CONFIRMED → agregar`), conferindo cada módulo contra a regra correspondente. Cada falha de teste apontava para um módulo; o truncamento em 200 linhas não tinha teste fornecido e apareceu na leitura do repositório (e confirmei pelo total de 300 linhas do CSV).
4. **Inspecionei os dados** (status, moedas, quartos, viradas de mês/ano, espaços, BOM, IDs duplicados) para garantir que não havia caso que exigisse tratamento adicional — os dados são consistentes, como diz o README.
5. **Corrigi cada defeito com a menor mudança possível**, rodando os testes a cada passo.
6. **Validei de forma independente:** escrevi um cálculo de referência separado (lê os CSVs direto, sem usar o código do projeto) e comparei o JSON inteiro (`summary`, `by_month`, `top_hotels`) para a amostra e para o dataset completo — resultado idêntico nos dois.
7. **Adicionei testes** em `tests/test_additional_rules.py` para as regras que os testes fornecidos não cobrem.

## Testes adicionados (`tests/test_additional_rules.py`)

- Noites: virada de mês, de ano, ano bissexto e multiplicação por quartos.
- Política de status: só `CONFIRMED` é faturável.
- Câmbio: multiplicação exata em `Decimal`.
- Arredondamento half-up (`0.005 → 0.01`, `0.025 → 0.03`) e arredondamento **só na serialização** (soma exata antes de arredondar).
- Leitura de mais de 200 linhas.
- `CANCELLED`/`NO_SHOW` fora de `by_month` e `top_hotels`.
- `by_month` pelo mês do check-in, em ordem ascendente.
- `top_hotels`: desempate por `hotel_id`, limite `--top` e soma de valores convertidos por hotel.
- Sem reservas faturáveis → `average_nightly_rate_brl == "0.00"`, listas vazias.
- Formato do relatório (chaves, `report_version`, offset `-03:00`).
- Amostra `exemplo-validacao.csv` idêntica à tabela do README.
- Dataset real: 300 reservas lidas.
- Códigos de saída: `--top` inválido (`0`, `-1`, `abc`) → `2`; arquivo inexistente → `2`; moeda sem taxa → `2`.

## Como validar

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest -q

PYTHONPATH=src python -m onfly_report \
  --input data/reservas_hoteis.csv \
  --rates data/taxas_cambio.csv \
  --output output/report.json

PYTHONPATH=src python -m onfly_report \
  --input data/exemplo-validacao.csv \
  --rates data/taxas_cambio.csv \
  --output output/exemplo.json
```

Saída esperada no stdout:

```
Reservas: 300 | Confirmadas: 235 | Noites: 1347 | Total BRL: 396170.00
Reservas: 12 | Confirmadas: 9 | Noites: 28 | Total BRL: 7566.00
```

## Resultado do `pytest`

```
$ pytest -q
..................................                                       [100%]
34 passed in 1.15s
```

(5 testes fornecidos, inalterados + 29 adicionais.) `ruff check src tests` → `All checks passed!`

## Resumo do relatório gerado (`reservas_hoteis.csv`)

```json
{
  "total_reservations": 300,
  "confirmed_reservations": 235,
  "cancelled_reservations": 31,
  "no_show_reservations": 34,
  "total_room_nights": 1347,
  "total_amount_brl": "396170.00",
  "average_nightly_rate_brl": "294.11"
}
```
