# 🧩 How to Use — Complete 2you

Guia rápido para executar a extração de PDFs via terminal.

---

## 🔧 Requisitos

1. Python 3.10+  
2. Instalar dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Criar arquivo `.env` na raiz (exemplo):
   ```env
   OPENAI_API_KEY=sk-EXEMPLO123456
   GPT_MODEL=gpt-5-mini
   ```

---

## ▶️ Execução

### 🧠 Sintaxe

```bash
python cli.py batch.json [pasta_pdfs] [pasta_output]
```

### 🧩 Exemplo prático

```bash
python cli.py batch_teste3.json teste3 output
```

---

## 🧠 O que acontece internamente

1. O script lê o `batch.json` (schemas e caminhos).  
2. Converte PDFs para texto via OCR/fitz.  
3. Aplica extração heurística via regex.  
4. Se falhar, aciona o GPT (fallback inteligente).  
5. Aprende novos padrões e salva resultados em JSON.

---

## 📊 Resultados

Os arquivos processados serão salvos em `output/` com sufixo `_output.json`.

Exemplo:
```
output/
 ┣ carteira_oab_1_output.json
 ┣ contrato_servico_1_output.json
 ┗ ...
```

Durante a execução, o terminal exibirá logs coloridos:

```
📄 [001/010] Processando: contrato_servico_1.pdf
✅ Extração completa (6 campos)
⚙️ Aprendido novo padrão: valor_total -> [\d,.]+
```

---

## 🧩 Encerramento

Após o batch, o script exibe:
- Total de arquivos processados
- Taxa de sucesso
- Campos aprendidos dinamicamente
- Tempo total de execução

---

### 💬 Dica

Para depuração detalhada:
```bash
python cli.py batch_teste3.json teste3 output --debug
```
