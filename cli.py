#!/usr/bin/env python3

import os, sys, json, re, time, logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
import traceback
from dotenv import load_dotenv

# 🎨 RICH IMPORTS (apenas personalização)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.logging import RichHandler
from rich.style import Style
from rich import print as rprint

# Inicializar console Rich
console = Console()

load_dotenv(".env", override=True)

try:
    import fitz
    HAS_FITZ = True
except:
    HAS_FITZ = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except:
    HAS_OPENAI = False



# ===== CONFIG =====

@dataclass
class Config:
    """Config centralizado"""
    gpt_model: str = os.getenv("GPT_MODEL", "gpt-5-mini")
    gpt_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gpt_timeout: int = 30
    gpt_max_tokens: int = 1500
    gpt_temperature: float = 1.0
    text_truncate_size: int = 2000
    gpt_threshold: float = 0.3
    log_level: str = "INFO"
    log_file: str = "extraction.log"
    log_to_console: bool = True
    batch_size: int = 100
    progress_interval: int = 10

def setup_logger(config: Config) -> logging.Logger:
    """Setup logger com Rich handler"""
    logger = logging.getLogger("extractor")
    logger.setLevel(getattr(logging, config.log_level))

    # 🎨 Rich handler para console
    if config.log_to_console:
        rh = RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
            show_level=True,
            show_path=False
        )
        rh.setLevel(logging.INFO)
        logger.addHandler(rh)

    # File handler tradicional
    fh = logging.FileHandler(config.log_file, encoding="utf-8")
    fh.setLevel(getattr(logging, config.log_level))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger

# ===== PATTERN TRACKER =====

class PatternSchema:
    def __init__(self, field: str, pattern: str, sample: str = None):
        self.field = field
        self.pattern = pattern
        self.count = 1

    def add_sample(self, sample):
        pass

    def to_dict(self) -> Dict:
        return {
            "field": self.field,
            "pattern": self.pattern,
            "occurrences": self.count
        }

# ===== EXTRACTOR =====

class ExtractorV2:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.global_patterns = {}
        self.label_schemas = {}
        self.current_pdf_path = ""
        self.gpt_client = None

        if HAS_OPENAI and config.gpt_api_key:
            try:
                self.gpt_client = OpenAI(api_key=config.gpt_api_key)
                self.logger.info(f"🤖 OpenAI inicializado com {config.gpt_model}")
            except Exception as e:
                self.logger.error(f"❌ Erro ao inicializar OpenAI: {e}")

    def _extract_oab(self, text, schema):
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        d = {f: None for f in schema}
        patterns_used = {}

        if "nome" in d:
            for line in lines:
                if re.fullmatch(r"(SUPLEMENTAR|ADVOGADO|ADVOGADA|ESTAGIÁRIO|ESTAGIARIO|ESTAGIARIA)", line, re.IGNORECASE):
                    continue
                if re.match(r"^[A-ZÇÁÉÍÓÚÂÃÕ'\s]+$", line) and len(line.split()) >= 2 and len(line) > 5:
                    if "INSCRI" not in line:
                        d["nome"] = line.strip()
                        patterns_used["nome"] = r"^[A-ZÇÁÉÍÓÚÂÃÕ'\s]+$"
                        break

        if "inscricao" in d or "seccional" in d:
            m = re.search(r"Inscri[cç][aã]o[\s\S]{0,50}?(\d{4,6})\s*([A-Z]{2})(?=\s|$)", text, re.IGNORECASE)
            if m:
                if "inscricao" in d:
                    d["inscricao"] = m.group(1)
                    patterns_used["inscricao"] = r"Inscri[cç][aã]o[\s\S]{0,50}?(\d{4,6})"
                if "seccional" in d:
                    d["seccional"] = m.group(2)
                    patterns_used["seccional"] = r"Inscri[cç][aã]o[\s\S]{0,50}?(\d{4,6})\s*([A-Z]{2})"

        if "subsecao" in d:
            m = re.search(r"(CONSELHO\s+SECCIONAL\s*-\s*[A-ZÇÁÉÍÓÚÂÃÕ ]+)", text, re.IGNORECASE)
            if m:
                d["subsecao"] = m.group(1).strip()
                patterns_used["subsecao"] = r"CONSELHO\s+SECCIONAL\s*-\s*[A-ZÇÁÉÍÓÚÂÃÕ ]+"

        if "categoria" in d:
            m = re.search(r"\b(SUPLEMENTAR|ADVOGADO|ADVOGADA|ESTAGIARIO|ESTAGIÁRIO|ESTAGIARIA)\b", text, re.IGNORECASE)
            if m:
                d["categoria"] = m.group(1).strip().title()
                patterns_used["categoria"] = r"(SUPLEMENTAR|ADVOGADO|ADVOGADA|ESTAGIARIO|ESTAGIÁRIO|ESTAGIARIA)"

        if "endereco_profissional" in d:
            m = re.search(r"(AVENIDA|RUA|AV\.|PRAÇA|PCA|RODOVIA)\s+[^\n]{5,120}", text, re.IGNORECASE)
            if m:
                d["endereco_profissional"] = m.group(0).strip()
                patterns_used["endereco_profissional"] = r"(AVENIDA|RUA|AV\.|PRAÇA|PCA|RODOVIA)\s+[^\n]{5,120}"

        if "telefone_profissional" in d:
            m = re.search(r"\(?\d{2}\)?[\s-]?\d{4,5}[-\s]?\d{4}", text)
            if m:
                d["telefone_profissional"] = m.group(0)
                patterns_used["telefone_profissional"] = r"\(?\d{2}\)?[\s-]?\d{4,5}[-\s]?\d{4}"

        if "situacao" in d:
            m = re.search(r"SITUA(?:C|Ç)[AÃ]O[\s:\n]*([A-ZÇÁÉÍÓÚÂÃÕ\s]+)", text, re.IGNORECASE)
            if m:
                d["situacao"] = m.group(1).strip()
                patterns_used["situacao"] = r"SITUA(?:C|Ç)[AÃ]O[\s:\n]*([A-ZÇÁÉÍÓÚÂÃÕ\s]+)"

        return d, patterns_used

    def _extract_tela(self, text, schema):
        d = {}
        patterns_used = {}
        self.logger.debug(f"_extract_tela: tentando extrair campos: {list(schema.keys())}")

        patterns = {
            "data_referencia": [r"(?:Data Referência|Data Reference)[\s:\n]+(\d{2}/\d{2}/\d{4})"],
            "data_base": [r"(?:Data Base|Data\s+Base)[\s:\n]+(\d{2}/\d{2}/\d{4})"],
            "data_vencimento": [r"(?:Data Vencimento|Data\s+Vencimento|Vcto[\s:\n]*)[\s:\n]*(\d{2}/\d{2}/\d{4})"],
            "valor_parcela": [r"(?:Vlr\.?\s*Parc\.?|Valor\s*Parcela|Vlr\.\s*Parc\.)[\s:\n]*([0-9,.]+)"],
            "quantidade_parcelas": [r"(?:Qtd\.?\s*Parcelas?|Quantidade\s+Parcelas?|Qtde\s+Parc\.?)[\s:\n]*(\d+)"],
            "total_de_parcelas": [r"Total[\s:\n]*([0-9,.]+)(?!\d)"],
            "selecao_de_parcelas": [r"(?:Seleção\s+de\s+parcelas|Selecao\s+de\s+parcelas)[\s:\n]*([^\n]+)"],
            "sistema": [r"(?:Dias\s+atraso\s+)?Sistema\s*[\n\s]*([A-ZÇÁÉÍÓÚÂÃÕ\s]+?)(?:\n|$)"],
            "produto": [r"(?:Saldo\s+Vencido|Saldo\s+a\s+Vencer)[\s\S]{0,150}?0\s+([A-ZÇÁÉÍÓÚÂÃÕ]+)(?:\n|$)"],
            "pesquisa_por": [r"(?:Pesquisa\s+Por|Pesquisa\s+por)[\s:\n]*([^\n]+?)(?:\n|$)"],
            "pesquisa_tipo": [r"(?:Pesquisa\s+Tipo|Tipo\s+de\s+pesquisa|Tipo)[\s:\n]*([^\n]+?)(?:\n|$)"],
            "cidade": [r"(?:Cidade|Municipio|Município)[\s:\n]*([A-ZÇÁÉÍÓÚÂÃÕ\s]+?)(?:\n|,|$)"],
        }

        for field, pats in patterns.items():
            if schema and field not in schema:
                continue

            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    value = m.group(1).strip() if m.lastindex else m.group(0).strip()

                    if not value or len(value) < 2:
                        continue
                    if value.lower() in ["n/a", "null", "none", "vazio"]:
                        continue

                    d[field] = value
                    patterns_used[field] = pat
                    self.logger.debug(f" ✓ {field}: {value[:30]}")
                    break

            if field not in d and field in (schema if schema else patterns.keys()):
                self.logger.debug(f" ✗ {field}: não encontrado")

        return d, patterns_used

    def _extract_pattern_from_value(self, field: str, value: str, text: str) -> Optional[str]:
        """
        Extrai padrões de valores com VALIDAÇÃO CONTEXTUAL.
        """
        if not value:
            return None

        field_lower = field.lower()
        value_str = str(value).strip()

        # Detecta datas (padrão já comprovado)
        if "data" in field_lower and re.match(r"\d{2}/\d{2}/\d{4}", value_str):
            return r"\d{2}/\d{2}/\d{4}"

        # 🔥 APRENDIZADO DINÂMICO DE VALORES MONETÁRIOS COM CONTEXTO

        if "valor" in field_lower or "parcela" in field_lower or "preco" in field_lower:

            # 1️⃣ REJEITAR: CPF, CNPJ, códigos bancários
            if re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}", value_str):
                self.logger.debug(f"❌ Rejeitado CPF/CNPJ format: {value_str}")
                return None

            if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", value_str):
                self.logger.debug(f"❌ Rejeitado CNPJ format: {value_str}")
                return None

            # 2️⃣ VALIDAR: Campo monetário deve ter contexto claro
            has_currency = any(sym in value_str for sym in ["R$", "$", "USD", "EUR"])
            has_comma = "," in value_str
            has_dot = "." in value_str

            # 3️⃣ BUSCAR CONTEXTO NO TEXTO
            text_lower = text.lower() if text else ""
            context_keywords = [
                "valor", "total", "preço", "preco", "custo",
                "importe", "montante", "importancia", "importancia"
            ]

            has_monetary_context = any(
                kw in text_lower for kw in context_keywords
            ) or has_currency

            # 4️⃣ DESCARTAR números muito curtos SEM contexto monetário explícito
            digit_count = len(re.findall(r"\d", value_str))

            if digit_count < 3 and not has_currency:
                self.logger.debug(f"❌ Número curto sem símbolo monetário: {value_str}")
                return None

            # 5️⃣ VALIDAR número não é apenas código de banco/agência
            if digit_count >= 3 and digit_count <= 5 and not has_currency and "." not in value_str:
                self.logger.debug(f"⚠️ Suspeita de código bancário: {value_str}")
                return None

            # 6️⃣ CONSTRUIR PADRÃO MONETÁRIO
            pattern_parts = []

            if has_currency:
                pattern_parts.append(r"(?:R\$|USD|EUR|\$)?\s*")
            else:
                context_pattern = r"(?:Valor|Total|Preço|Preco|Custo|Importe|Documento|Montante)[\s:]*"

                if re.search(context_pattern, text, re.IGNORECASE):
                    pattern_parts.append(context_pattern)
                    pattern_parts.append(r"(?:R\$)?\s*")
                else:
                    self.logger.debug(f"❌ Número sem contexto monetário no texto: {value_str}")
                    return None

            pattern_parts.append(r"\d{1,3}(?:[\.,]\d{3})*")

            if has_comma or has_dot:
                pattern_parts.append(r"(?:[.,]\d{2})?")

            pattern = "".join(pattern_parts)

            self.logger.debug(f"✅ Padrão monetário criado: {pattern}")
            return pattern

        # Campos numéricos genéricos
        if "quantidade" in field_lower or "qtd" in field_lower:
            return r"\d+"

        if "codigo" in field_lower or "inscricao" in field_lower:
            return r"\d{4,6}"

        if "email" in field_lower:
            return r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

        if "telefone" in field_lower or "celular" in field_lower:
            return r"\(?\d{2}\)?\s?-?\d{4,5}[-\s]?\d{4}"

        if "nome" in field_lower or "descricao" in field_lower:
            if re.match(r"^[A-ZÇÁÉÍÓÚÂÃÕ\s'-]+$", value_str):
                return r"^[A-ZÇÁÉÍÓÚÂÃÕ\s'-]+$"

        if "estado" in field_lower or "uf" in field_lower:
            if re.match(r"^[A-Z]{2}$", value_str):
                return r"[A-Z]{2}"

        return None

    def _fill_with_gpt(self, label: str, text: str, null_fields: List[str]) -> Tuple[Dict, Dict]:
        if not self.gpt_client or not null_fields:
            return {}, {}

        truncated = text[:self.config.text_truncate_size]

        prompt = f"Extraia estes campos em JSON: {json.dumps(null_fields)}\n\nTexto:\n{truncated}\n\nPS:valor que não existe recebe null, NÃO INVENTE VALORES"

        try:
            resp = self.gpt_client.chat.completions.create(
                model=self.config.gpt_model,
                messages=[
                    {"role": "system", "content": "RESPONDA APENAS COM JSON VÁLIDO."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.gpt_temperature,
                max_completion_tokens=self.config.gpt_max_tokens,
                timeout=self.config.gpt_timeout,
            )

            content = resp.choices[0].message.content

            if not content or len(content.strip()) < 5:
                return {}, {}

            try:
                data = json.loads(content)
                for k, v in data.items():
                    if v is not None and k in null_fields:
                        pattern = self._extract_pattern_from_value(k, v, text)
                        if pattern:
                            if k not in self.global_patterns:
                                self.global_patterns[k] = PatternSchema(k, pattern, v)
                                self.logger.debug(f"Padrão aprendido para '{k}': {pattern[:50]}")
                            else:
                                self.global_patterns[k].add_sample(v)
                                self.global_patterns[k].count += 1

                return data, {}

            except json.JSONDecodeError:
                m = re.search(r"(\{.*?\})", content, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        for k, v in data.items():
                            if v is not None and k in null_fields:
                                pattern = self._extract_pattern_from_value(k, v, text)
                                if pattern and k not in self.global_patterns:
                                    self.global_patterns[k] = PatternSchema(k, pattern, v)
                        return data, {}
                    except:
                        pass

            return {}, {}

        except Exception as e:
            self.logger.warning(f"Erro GPT: {type(e).__name__}: {str(e)[:100]}")
            return {}, {}

    def extract(self, text: str, schema: Dict[str, str], label: str) -> Dict[str, Any]:
        text = text or ""
        d = {f: None for f in schema}
        sources = {f: None for f in schema}

        # 1. Regex
        if "oab" in label.lower():
            regex_result, patterns_used = self._extract_oab(text, schema)
        elif "tela" in label.lower():
            regex_result, patterns_used = self._extract_tela(text, schema)
        else:
            regex_result = {}
            patterns_used = {}

        for k, v in regex_result.items():
            if k in d and v is not None:
                d[k] = v
                sources[k] = "regex"

            if k in patterns_used:
                if k not in self.global_patterns:
                    self.global_patterns[k] = PatternSchema(k, patterns_used[k], v)
                else:
                    self.global_patterns[k].add_sample(v)
                    self.global_patterns[k].count += 1

        # 2. ✅ PADRÕES GLOBAIS (reutilizar ANTES de IA!)
        for field in [f for f in d if d[f] is None]:
            if field in self.global_patterns:
                pattern = self.global_patterns[field].pattern
                m = re.search(pattern, text)
                if m:
                    value = m.group(1) if m.lastindex else m.group(0)
                    if value and len(str(value).strip()) > 1:
                        d[field] = value
                        sources[field] = "regex_global"
                        self.global_patterns[field].count += 1

        # 3. GPT - Apenas se >=30% nulos
        null_fields = [f for f, v in d.items() if v is None]
        null_pct = len(null_fields) / len(schema) if schema else 0

        if null_fields and null_pct >= self.config.gpt_threshold and self.gpt_client:
            self.logger.debug(f"{label}: {null_pct:.0%} nulos → IA acionada")
            gpt_result, _ = self._fill_with_gpt(label, text, null_fields)

            for k, v in gpt_result.items():
                if v is not None and k in d and d[k] is None:
                    d[k] = v
                    sources[k] = "gpt"

        d["_sources"] = sources
        return d

# ===== PDF UTILS =====

def extract_text_from_pdf(path: str, logger: logging.Logger) -> Optional[str]:
    if not HAS_FITZ:
        logger.error("PyMuPDF não disponível")
        return None

    try:
        doc = fitz.open(path)
        txt = "\n".join(p.get_text("text") for p in doc)
        doc.close()
        return txt
    except Exception as e:
        logger.error(f"Erro ao ler {path}: {str(e)[:100]}")
        return None

# ===== MAIN =====

def process_batch(batch_file: str, files_dir: str, output_dir: str, config: Config):
    logger = setup_logger(config)
    os.makedirs(output_dir, exist_ok=True)

    # 🎨 Panel com título
    console.print(Panel(
        "[bold cyan]🚀 EXTRAÇÃO EM BATCH[/bold cyan]",
        expand=False,
        border_style="cyan"
    ))

    try:
        with open(batch_file, "r", encoding="utf-8") as f:
            batch = json.load(f)
    except Exception as e:
        console.print(f"[bold red]❌ Erro ao ler batch.json: {e}[/bold red]")
        return

    extractor = ExtractorV2(config, logger)
    total_files = len(batch)
    successful = 0
    failed = 0

    logger.info(f"Total de arquivos: {total_files}")

    start_time = time.time()

    # 🎨 Progress bar com Rich
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task(f"Processando {total_files} arquivos...", total=total_files)

        for idx, item in enumerate(batch, 1):
            file_start = time.time()
            fname = Path(item["pdf_path"]).name

            try:
                pdf_path = os.path.join(files_dir, item["pdf_path"])
                text = extract_text_from_pdf(pdf_path, logger)

                if not text:
                    logger.warning(f"❌ Falha leitura: {fname}")
                    failed += 1
                    progress.update(task, advance=1)
                    continue

                extractor.current_pdf_path = pdf_path
                result = extractor.extract(text, item["extraction_schema"], item["label"])

                fields_only = {k: result.get(k) for k in item["extraction_schema"].keys()}
                filled = sum(1 for v in fields_only.values() if v is not None)
                total = len(item["extraction_schema"])

                output = {**fields_only}
                output["_metadata"] = {
                    "label": item["label"],
                    "pdf_path": item["pdf_path"],
                    "filled_fields": filled,
                    "total_fields": total,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                output["_sources"] = result.get("_sources", {})

                out_path = os.path.join(output_dir, Path(pdf_path).stem + "_output.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)

                duration_ms = (time.time() - file_start) * 1000

                # 🎨 Log colorido
                if filled == total:
                    logger.info(f"✅ {fname}: {filled}/{total} ({duration_ms:.0f}ms)")
                else:
                    logger.info(f"⚠️  {fname}: {filled}/{total} ({duration_ms:.0f}ms)")

                successful += 1
                progress.update(task, advance=1)

            except Exception as e:
                logger.error(f"❌ Erro em {fname}: {str(e)[:100]}")
                logger.debug(traceback.format_exc())
                failed += 1
                progress.update(task, advance=1)

    total_time = time.time() - start_time

    # 🎨 Tabela de resumo com Rich
    summary_table = Table(title="📊 RESUMO DA EXTRAÇÃO", expand=False)
    summary_table.add_column("Métrica", style="cyan")
    summary_table.add_column("Valor", style="green")

    summary_table.add_row("✅ Sucesso", str(successful))
    summary_table.add_row("❌ Falha", str(failed))
    summary_table.add_row("⏱️  Tempo Total", f"{total_time:.1f}s")
    summary_table.add_row("📈 Taxa Sucesso", f"{100*successful/total_files:.1f}%")

    console.print(summary_table)

    # 🎨 Padrões aprendidos em tabela
    if extractor.global_patterns:
        patterns_table = Table(title="🧠 PADRÕES APRENDIDOS", expand=False)
        patterns_table.add_column("Campo", style="magenta")
        patterns_table.add_column("Padrão", style="yellow")
        patterns_table.add_column("Ocorrências", style="cyan")

        for field, pattern_schema in sorted(extractor.global_patterns.items()):
            schema_dict = pattern_schema.to_dict()
            pattern_short = schema_dict['pattern'][:40] + "..." if len(schema_dict['pattern']) > 40 else schema_dict['pattern']
            patterns_table.add_row(field, pattern_short, str(schema_dict['occurrences']))

        console.print(patterns_table)

    logger.info(f"Log completo: {config.log_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[bold red]Uso:[/bold red] python cli.py batch.json [files_dir] [output_dir]")
        sys.exit(1)

    batch = sys.argv[1]
    files = sys.argv[2] if len(sys.argv) > 2 else "files"
    out = sys.argv[3] if len(sys.argv) > 3 else "output"

    config = Config()
    process_batch(batch, files, out, config)
