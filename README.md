# 🧠 Complete 2you — PDF Information Extractor

### 🚀 Enter AI Fellowship — Take Home Project

Solução completa para extração estruturada de informações a partir de PDFs, com foco em **eficiência**, **baixo custo**, **aprendizado adaptativo** e **robustez sob ruído**.

---

## ⚙️ Arquitetura

O fluxo é dividido em três níveis complementares:

1. **Regex Heurístico (Nível 0)**
   - Alguns padrões regex pré escritos manualmente baseados em casos gerais são carregados.
   - Extração direta via expressões regulares otimizadas.
   - Ideal para campos padronizados (datas, valores, nomes, etc).

3. **Aprendizado Dinâmico (Nível 1)**  
   - Regexs aprendem automaticamente novos padrões a partir de valores extraídos.
   - Reutiliza padrões entre labels diferentes (transfer learning textual).

4. **Fallback GPT (Nível 2)**  
   - Executado apenas em **~30% dos casos** quando o heurístico não resolve.
   - Modelo: `gpt-5-mini`, com truncamento e validação contextual.
   - Padrões corretos aprendidos pelo GPT são armazenados e reaproveitados.

---

## 🧠 Destaques Técnicos

| Componente | Descrição |
|-------------|------------|
| 🔍 **Aprendizado Regex Dinâmico** | Gera e armazena padrões automáticos com base em extrações bem-sucedidas. |
| 🧩 **Reuso Global de Padrões** | Campos como `nome`, `valor`, `data_emissao` são reconhecidos entre schemas diferentes. |
| 🧠 **Fallback Inteligente** | GPT é chamado apenas se o heurístico falhar, reduzindo o custo em até 70%. |
| 📊 **Logs Detalhados** | Progresso, tempo e acurácia por arquivo são registrados. |
| ⚙️ **Escalável** | Capaz de processar até 1000 PDFs em batch com controle de workers. |

---


## 🧱 Estrutura de Pastas

```
📦 projeto/
 ┣ 📜 cli.py
 ┣ 📜 batch.json
 ┣ 📁 files/
 ┣ 📁 output/
 ┗ 📜 .env
```

---

## ✍️ Autor

**Carlos Guerra**   
Linkedin: https://www.linkedin.com/in/carlos-guerra-24853914a/
