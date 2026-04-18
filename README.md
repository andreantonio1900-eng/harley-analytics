# harley-analytics

Projeto local para consultar `frota_harley.duckdb` de forma mais intuitiva.

## Estrutura esperada

```text
harley_analytics_v2/
├── app/
├── data/
│   └── frota_harley.duckdb
└── pyproject.toml
```

## Instalação

```bash
cd harley_analytics_v2
python3 -m pip install -e .
```

## Teste rápido

```bash
harley info
harley modelos --ano 2025 --competencia 2026-03-01
harley share-uf --competencia 2026-03-01
harley frota-modelo --modelo "H-D/F LHXSE" --competencia 2026-03-01
harley variacao-modelo --modelo "HARLEY DAVIDSON/FLHTK" --de 2024-10-01 --para 2024-11-01
harley familia --pattern "%RA1250%"
```

## Observações

- O banco padrão é `data/frota_harley.duckdb`, relativo à raiz do projeto.
- Você pode sobrescrever com `--db caminho/para/arquivo.duckdb`.
- As funções de variação operam no nível do **modelo agregado**, não por bucket municipal.
